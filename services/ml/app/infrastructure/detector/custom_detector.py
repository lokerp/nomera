"""
Custom "Frankenstein" ALPR detector.

Pipeline:
  1. open-image-models (YOLOv9 ONNX) → license plate bounding-box detection
  2. PaddleOCR (PP-OCRv5) → text detection inside cropped plate, perspective correction, recognition
  3. Post-processing → regex filter for Russian license plate format
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np

from app.domain.interfaces import IPlateDetector
from app.domain.models import BoundingBox, PlateDetection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure vendored open-image-models is importable
# ---------------------------------------------------------------------------
_OIM_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "open-image-models"
if str(_OIM_ROOT) not in sys.path:
    sys.path.insert(0, str(_OIM_ROOT))

# ---------------------------------------------------------------------------
# Russian plate regex
# ---------------------------------------------------------------------------
# Standard format: 1 letter, 3 digits, 2 letters, 2-3 digit region code
# Only the 12 Cyrillic letters that have Latin look-alikes are used.
#
# PaddleOCR returns Latin chars (lang='en'), so we accept both Cyrillic and
# Latin look-alikes and normalise to Cyrillic afterwards.
_CYRILLIC_ALLOWED = "АВЕКМНОРСТУХ"
_LATIN_LOOKALIKES = "ABEKMHOPCTYX"

# Mapping Latin → Cyrillic for normalisation
_LATIN_TO_CYRILLIC = dict(zip(_LATIN_LOOKALIKES, _CYRILLIC_ALLOWED))

# Accept either Cyrillic or Latin look-alikes in the letter positions
_LETTER = f"[{_CYRILLIC_ALLOWED}{_LATIN_LOOKALIKES}]"
_RU_PLATE_RE = re.compile(
    rf"^{_LETTER}\d{{3}}{_LETTER}{{2}}\d{{2,3}}$",
    re.IGNORECASE,
)

# Bbox padding factor — expand each side by this fraction of w/h to avoid
# clipping plate edges.
_BBOX_PAD_FACTOR = 0.10


def _normalise_plate(text: str) -> str:
    """Upper-case and replace Latin look-alikes with Cyrillic equivalents."""
    text = text.upper().strip()
    return "".join(_LATIN_TO_CYRILLIC.get(ch, ch) for ch in text)


# ---------------------------------------------------------------------------
# Position-aware OCR fix-up
# ---------------------------------------------------------------------------
# Russian plate layout (0-indexed):
#   pos 0   letter
#   pos 1-3 digits
#   pos 4-5 letters
#   pos 6-7 digits (+ optional pos 8 digit for 3-digit region)
_LETTER_POSITIONS = (0, 4, 5)
_DIGIT_POSITIONS_8 = (1, 2, 3, 6, 7)
_DIGIT_POSITIONS_9 = (1, 2, 3, 6, 7, 8)

_PLATE_LETTERS_LATIN = set(_LATIN_LOOKALIKES)
_PLATE_LETTERS_CYR = set(_CYRILLIC_ALLOWED)
_PLATE_DIGITS = set("0123456789")

# When a letter is expected but OCR returned a digit → most likely substitution
_DIGIT_TO_LETTER = {
    "0": "O",
    "8": "B",
    "1": "T",
    "4": "A",
    "6": "B",
    "3": "E",
    "7": "T",
    "5": "S",  # S not in plates, but PaddleOCR may emit it for С
}

# When a digit is expected but OCR returned a letter
_LETTER_TO_DIGIT = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "B": "8",
    "I": "1",
    "L": "1",
    "T": "7",
    "Z": "2",
    "S": "5",
    "G": "6",
    "E": "3",
    "A": "4",
    # Cyrillic look-alikes too, in case OCR emitted Cyrillic
    "О": "0",
    "В": "8",
    "Т": "7",
    "З": "3",
}


# ---------------------------------------------------------------------------
# Plate crop pre-processing for better OCR
# ---------------------------------------------------------------------------
# PaddleOCR is trained on text at ~32-48px height. Small / dim plate crops
# benefit a lot from upscaling + contrast enhancement before recognition.
_MIN_OCR_HEIGHT = 64
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def _preprocess_plate(crop: np.ndarray) -> np.ndarray:
    """
    Improve readability of a plate crop for PaddleOCR.

    * Upscale to a minimum height while preserving aspect ratio.
    * CLAHE on the L channel to even out lighting (shadows, glare).
    * Mild bilateral filter to denoise without blurring strokes.
    """
    if crop.size == 0:
        return crop

    h, w = crop.shape[:2]
    if h < _MIN_OCR_HEIGHT:
        scale = _MIN_OCR_HEIGHT / h
        new_w = max(1, int(round(w * scale)))
        crop = cv2.resize(crop, (new_w, _MIN_OCR_HEIGHT), interpolation=cv2.INTER_CUBIC)

    # CLAHE in LAB space — improves contrast without distorting colour
    if crop.ndim == 3 and crop.shape[2] == 3:
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = _CLAHE.apply(l)
        crop = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    # Light denoise — preserve strokes
    crop = cv2.bilateralFilter(crop, d=5, sigmaColor=40, sigmaSpace=40)

    return crop


def _coerce_to_plate(raw: str) -> str | None:
    """
    Try to coerce *raw* OCR text into a valid Russian plate by substituting
    confusable characters at known letter/digit positions.

    Returns the Cyrillic-normalised plate on success, None otherwise.
    """
    if not raw:
        return None
    # Strip everything but A-Z / А-Я / digits, uppercase
    cleaned = re.sub(r"[^A-ZА-Я0-9]", "", raw.upper())
    if len(cleaned) not in (8, 9):
        return None

    digit_positions = _DIGIT_POSITIONS_8 if len(cleaned) == 8 else _DIGIT_POSITIONS_9
    fixed: list[str] = list(cleaned)

    for pos in _LETTER_POSITIONS:
        ch = fixed[pos]
        if ch in _PLATE_LETTERS_LATIN or ch in _PLATE_LETTERS_CYR:
            continue
        sub = _DIGIT_TO_LETTER.get(ch)
        if sub is None:
            return None
        fixed[pos] = sub

    for pos in digit_positions:
        ch = fixed[pos]
        if ch in _PLATE_DIGITS:
            continue
        sub = _LETTER_TO_DIGIT.get(ch)
        if sub is None:
            return None
        fixed[pos] = sub

    candidate = _normalise_plate("".join(fixed))
    if _RU_PLATE_RE.match(candidate):
        return candidate
    return None


def _pad_bbox(
    x1: int, y1: int, x2: int, y2: int,
    img_w: int, img_h: int,
    pad: float = _BBOX_PAD_FACTOR,
) -> tuple[int, int, int, int]:
    """Expand bounding box by *pad* fraction, clamped to image bounds."""
    w = x2 - x1
    h = y2 - y1
    dx = int(w * pad)
    dy = int(h * pad)
    return (
        max(0, x1 - dx),
        max(0, y1 - dy),
        min(img_w, x2 + dx),
        min(img_h, y2 + dy),
    )


class CustomDetector(IPlateDetector):
    """
    Frankenstein ALPR: open-image-models detection + PaddleOCR recognition.
    """

    def __init__(
        self,
        detector_model: str = "yolo-v9-s-608-license-plate-end2end",
        detector_conf: float = 0.4,
        ocr_lang: str = "en",
        bbox_pad: float = _BBOX_PAD_FACTOR,
        use_gpu: bool = True,
    ) -> None:
        self._detector_model = detector_model
        self._detector_conf = detector_conf
        self._ocr_lang = ocr_lang
        self._bbox_pad = bbox_pad
        self._use_gpu = use_gpu

        self._lp_detector = None  # LicensePlateDetector
        self._ocr = None          # PaddleOCR

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timed_warmup_predict(self, fn, dummy: np.ndarray, timeout: int, label: str) -> None:
        """Run fn(dummy) in a thread. Log a warning and continue if it times out."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(fn, dummy)
            try:
                future.result(timeout=timeout)
                logger.info("%s warm-up OK", label)
            except concurrent.futures.TimeoutError:
                logger.warning("%s warm-up timed out after %ds — skipping (will init on first frame)", label, timeout)
            except Exception:
                logger.warning("%s warm-up predict failed (non-fatal)", label, exc_info=True)

    def _init_ocr(self, device: str):
        from paddleocr import PaddleOCR

        logger.info("Loading PaddleOCR (lang=%s, device=%s) ...", self._ocr_lang, device)
        try:
            ocr = PaddleOCR(
                lang=self._ocr_lang,
                device=device,
                enable_mkldnn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            logger.info("PaddleOCR initialised on %s", device)
            return ocr
        except Exception as exc:
            if device != "cpu":
                logger.warning(
                    "PaddleOCR GPU init failed (%s), retrying on CPU ...", exc
                )
                return self._init_ocr("cpu")
            raise

    # ------------------------------------------------------------------
    # Warm-up
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Load models and warm up."""
        if self._lp_detector is not None:
            return

        # Disable OneDNN — crashes on some platforms (ConvertPirAttribute2RuntimeAttribute bug)
        os.environ["FLAGS_use_mkldnn"] = "0"
        # Skip HuggingFace/CDN connectivity pre-check — it blocks startup for 5-10s
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        # 1. Plate detector (open-image-models via ONNX)
        from open_image_models import LicensePlateDetector

        logger.info(
            "Loading open-image-models plate detector: %s (conf=%.2f)",
            self._detector_model,
            self._detector_conf,
        )
        self._lp_detector = LicensePlateDetector(
            detection_model=self._detector_model,
            conf_thresh=self._detector_conf,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

        # 2. PaddleOCR — try GPU, fall back to CPU if init hangs or crashes
        from paddleocr import PaddleOCR

        device = "gpu" if self._use_gpu else "cpu"
        self._ocr = self._init_ocr(device)

        # 3. Warm-up: trigger JIT / model load before first real frame.
        # Run in a thread with a timeout so a hung GPU init can't block startup.
        logger.info("Running warm-up inference ...")
        dummy = np.zeros((64, 128, 3), dtype=np.uint8)
        self._timed_warmup_predict(self._lp_detector.predict, dummy, timeout=60, label="YOLO")
        self._timed_warmup_predict(self._ocr.predict, dummy, timeout=120, label="PaddleOCR")

        logger.info("Custom (Frankenstein) ALPR pipeline ready")

        logger.info("Custom (Frankenstein) ALPR pipeline ready")

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, frames: list[np.ndarray]) -> list[list[PlateDetection]]:
        if self._lp_detector is None:
            self.warmup()

        if not frames:
            return []

        all_detections: list[list[PlateDetection]] = []

        for frame in frames:
            frame_h, frame_w = frame.shape[:2]
            frame_detections: list[PlateDetection] = []

            # Step 1 — detect plate bounding boxes
            try:
                det_results = self._lp_detector.predict(frame)
            except Exception:
                logger.exception("Plate detection failed on frame")
                all_detections.append([])
                continue

            if det_results:
                logger.debug("YOLO: %d bbox(es) in frame %dx%d", len(det_results), frame_w, frame_h)

            for det in det_results:
                bbox = det.bounding_box
                conf = float(det.confidence)

                # Pad the bbox to avoid clipping plate edges
                x1, y1, x2, y2 = _pad_bbox(
                    bbox.x1, bbox.y1, bbox.x2, bbox.y2,
                    frame_w, frame_h,
                    self._bbox_pad,
                )

                logger.info(
                    "YOLO bbox [%d,%d,%d,%d] conf=%.2f",
                    x1, y1, x2, y2, conf,
                )

                # Crop plate region
                plate_crop = frame[y1:y2, x1:x2]
                if plate_crop.size == 0:
                    logger.debug("  → skipped: empty crop")
                    continue

                # Pre-process: upscale tiny crops + CLAHE + denoise
                plate_crop = _preprocess_plate(plate_crop)

                # Step 2 — PaddleOCR on the crop
                try:
                    ocr_results = self._ocr.predict(plate_crop)
                except Exception:
                    logger.exception("PaddleOCR failed on plate crop [%d,%d,%d,%d]", x1, y1, x2, y2)
                    continue

                if not ocr_results:
                    logger.info("  → OCR: no result returned")
                    continue

                # PaddleOCR 3.5 returns list of OCRResult dict-like objects.
                # Each has: rec_texts (list[str]), rec_scores (list[float])
                ocr_res = ocr_results[0]
                rec_texts = ocr_res.get("rec_texts", [])
                rec_scores = ocr_res.get("rec_scores", [])

                logger.info(
                    "  → OCR: texts=%r scores=%s",
                    rec_texts,
                    [f"{s:.2f}" for s in rec_scores],
                )

                if not rec_texts:
                    logger.info("  → OCR: empty texts list")
                    continue

                # Try each recognised text fragment individually first
                best_plate_text: str | None = None
                best_ocr_conf: float = 0.0

                for text_raw, score in zip(rec_texts, rec_scores):
                    # Strip spaces and non-alphanumeric
                    candidate = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]", "", text_raw)
                    if not candidate:
                        continue

                    normalised = _normalise_plate(candidate)

                    # Step 3 — regex filter for Russian plates
                    if _RU_PLATE_RE.match(normalised):
                        if score > best_ocr_conf:
                            best_plate_text = normalised
                            best_ocr_conf = float(score)
                    else:
                        # Try position-aware fix for confusable chars (O↔0, B↔8, …)
                        coerced = _coerce_to_plate(candidate)
                        if coerced is not None:
                            # Apply a small penalty since this required correction
                            adj_score = float(score) * 0.9
                            if adj_score > best_ocr_conf:
                                best_plate_text = coerced
                                best_ocr_conf = adj_score
                            logger.info("  → coerced %r → %r (score=%.2f)", text_raw, coerced, adj_score)
                        else:
                            logger.debug("  → regex no match: %r → %r", text_raw, normalised)

                if best_plate_text is None:
                    # Fallback: concatenate all text fragments
                    # (plates can be split across two lines by OCR)
                    all_text = ""
                    total_conf = 0.0
                    for text_raw, score in zip(rec_texts, rec_scores):
                        fragment = re.sub(r"[^A-Za-zА-Яа-яЁё0-9]", "", text_raw)
                        all_text += fragment
                        total_conf += float(score)

                    n_parts = len(rec_texts)
                    normalised = _normalise_plate(all_text)
                    if _RU_PLATE_RE.match(normalised) and n_parts > 0:
                        best_plate_text = normalised
                        best_ocr_conf = total_conf / n_parts
                        logger.debug("  → regex matched via concat: %r", best_plate_text)
                    else:
                        # Try coercion on concatenated text too
                        coerced = _coerce_to_plate(all_text)
                        if coerced is not None and n_parts > 0:
                            best_plate_text = coerced
                            best_ocr_conf = (total_conf / n_parts) * 0.9
                            logger.info("  → coerced concat %r → %r", all_text, coerced)
                        else:
                            logger.info("  → regex no match (concat): %r → %r", all_text, normalised)

                if best_plate_text is None:
                    continue

                combined_conf = (conf + best_ocr_conf) / 2

                plate = PlateDetection(
                    plate_text=best_plate_text,
                    bbox=BoundingBox(
                        x1=float(x1),
                        y1=float(y1),
                        x2=float(x2),
                        y2=float(y2),
                        confidence=conf,
                    ),
                    region_name="ru",
                    confidence=combined_conf,
                    frame_number=0,   # caller sets this
                    timestamp=0.0,    # caller sets this
                )
                frame_detections.append(plate)

            all_detections.append(frame_detections)

        return all_detections
