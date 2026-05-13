"""
Keypoint-based plate detector.

Uses a YOLOv8-Pose model that emits the four plate corners
(TL/TR/BR/BL) in addition to a bounding box. The corners are run through
`cv2.getPerspectiveTransform` + `cv2.warpPerspective` so the OCR receives
a frontal, rectangular plate crop instead of a perspective-skewed bbox
crop with surrounding clutter. OCR itself is the same `fast-plate-ocr`
pipeline used by the bbox detector.
"""
from __future__ import annotations

import logging
import statistics
from pathlib import Path

import cv2
import numpy as np

from app.domain.interfaces import IPlateDetector
from app.domain.models import BoundingBox, PlateDetection

logger = logging.getLogger(__name__)


class KeypointAlprDetector(IPlateDetector):
    """
    Pose-model-driven plate detector with perspective-corrected OCR.

    The YOLOv8-Pose checkpoint is consumed via Ultralytics (PyTorch),
    OCR is the same fast-plate-ocr LicensePlateRecognizer used elsewhere.
    """

    def __init__(
        self,
        keypoint_model_path: str,
        detector_conf: float = 0.25,
        keypoint_conf: float = 0.5,
        min_avg_keypoint_conf: float = 0.6,
        ocr_model: str = "",
        ocr_model_path: str = "",
        ocr_config_path: str = "",
        warp_min_size: tuple[int, int] = (192, 96),
        max_skew_ratio: float = 1.6,
        min_ocr_confidence: float = 0.0,
    ) -> None:
        self._keypoint_model_path = keypoint_model_path
        self._detector_conf = detector_conf
        self._keypoint_conf = keypoint_conf
        self._min_avg_keypoint_conf = min_avg_keypoint_conf
        self._ocr_model = ocr_model
        self._ocr_model_path = ocr_model_path
        self._ocr_config_path = ocr_config_path
        self._warp_min_w, self._warp_min_h = warp_min_size
        self._max_skew_ratio = max(1.0, float(max_skew_ratio))
        self._min_ocr_confidence = float(min_ocr_confidence)

        self._yolo = None
        self._ocr = None
        self._device = "cpu"

    def warmup(self) -> None:
        if self._yolo is not None and self._ocr is not None:
            return

        from app.config import SERVICE_ROOT

        # Lazy-import heavy deps so import failures surface at warmup time only.
        import torch
        from fast_plate_ocr import LicensePlateRecognizer
        from ultralytics import YOLO

        model_path = Path(self._keypoint_model_path)
        if not model_path.is_absolute():
            model_path = SERVICE_ROOT / model_path
        if not model_path.exists():
            raise FileNotFoundError(f"Keypoint model not found: {model_path}")

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading keypoint detector: %s (device=%s)", model_path, self._device)

        self._yolo = YOLO(str(model_path))
        # Run a small dummy frame to fully initialize CUDA streams / fuse layers.
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self._yolo.predict(dummy, conf=self._detector_conf, verbose=False, device=self._device)

        # --- OCR ---
        ocr_kwargs: dict = {}
        if self._ocr_model_path:
            ocr_path = Path(self._ocr_model_path)
            if not ocr_path.is_absolute():
                ocr_path = SERVICE_ROOT / ocr_path

            cfg_path = Path(self._ocr_config_path) if self._ocr_config_path else None
            if cfg_path and not cfg_path.is_absolute():
                cfg_path = SERVICE_ROOT / cfg_path

            logger.info("Loading custom OCR: %s (config=%s)", ocr_path, cfg_path)
            ocr_kwargs["onnx_model_path"] = str(ocr_path)
            if cfg_path:
                ocr_kwargs["plate_config_path"] = str(cfg_path)
            ocr_kwargs["hub_ocr_model"] = None
        else:
            logger.info("Loading hub OCR model: %s", self._ocr_model)
            ocr_kwargs["hub_ocr_model"] = self._ocr_model or None

        self._ocr = LicensePlateRecognizer(
            device="cuda" if self._device == "cuda" else "cpu",
            **ocr_kwargs,
        )

        # Warm up OCR with a dummy crop matching its expected color mode.
        cfg = self._ocr.config
        dummy_h = getattr(cfg, "img_height", 64) or 64
        dummy_w = getattr(cfg, "img_width", 128) or 128
        if getattr(cfg, "image_color_mode", "rgb") == "grayscale":
            dummy_crop = np.zeros((dummy_h, dummy_w), dtype=np.uint8)
        else:
            dummy_crop = np.zeros((dummy_h, dummy_w, 3), dtype=np.uint8)
        self._ocr.run_one(dummy_crop, return_confidence=True)

        logger.info("Keypoint ALPR pipeline ready")

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        """
        Sort 4 points into TL / TR / BR / BL.

        The pose model already outputs them in that order, but real-world
        plates can be rotated past ~45° and label order can drift, so we
        re-sort defensively the same way the upstream inference script does.
        """
        pts = np.asarray(pts, dtype=np.float32)
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # TL
        rect[2] = pts[np.argmax(s)]   # BR
        diff = np.diff(pts, axis=1).ravel()
        rect[1] = pts[np.argmin(diff)]  # TR
        rect[3] = pts[np.argmax(diff)]  # BL
        return rect

    def _quad_geometry(self, corners: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        """
        Returns (ordered_corners, target_w, target_h, skew_ratio).

        skew_ratio = max(opposing-side-length-ratios) — close to 1.0 means
        the plate is seen frontally; higher means heavy perspective.
        """
        ordered = self._order_corners(corners)
        w_top = float(np.linalg.norm(ordered[1] - ordered[0]))
        w_bot = float(np.linalg.norm(ordered[2] - ordered[3]))
        h_left = float(np.linalg.norm(ordered[3] - ordered[0]))
        h_right = float(np.linalg.norm(ordered[2] - ordered[1]))

        target_w = max(w_top, w_bot)
        target_h = max(h_left, h_right)

        eps = 1e-6
        skew_w = max(w_top, w_bot) / max(min(w_top, w_bot), eps)
        skew_h = max(h_left, h_right) / max(min(h_left, h_right), eps)
        skew_ratio = max(skew_w, skew_h)
        return ordered, target_w, target_h, skew_ratio

    def _warp_plate(
        self, frame: np.ndarray, ordered: np.ndarray, target_w: float, target_h: float
    ) -> np.ndarray | None:
        """Perspective-warp a plate quadrilateral into a frontal crop."""
        target_w = int(round(target_w))
        target_h = int(round(target_h))
        if target_w < 10 or target_h < 5:
            return None

        # Upscale slightly so the OCR doesn't lose detail when it resizes
        # down to its training input; capped by the source pixel budget.
        target_w = max(target_w, self._warp_min_w)
        target_h = max(target_h, self._warp_min_h)

        dst = np.array(
            [
                [0, 0],
                [target_w - 1, 0],
                [target_w - 1, target_h - 1],
                [0, target_h - 1],
            ],
            dtype=np.float32,
        )
        m = cv2.getPerspectiveTransform(ordered, dst)
        return cv2.warpPerspective(
            frame, m, (target_w, target_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    def _run_ocr(self, plate_crop: np.ndarray):
        """Run the OCR head on an already-rectified plate crop (BGR)."""
        cfg = self._ocr.config
        color_mode = getattr(cfg, "image_color_mode", "rgb")
        if color_mode == "grayscale":
            crop = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        elif color_mode == "rgb":
            crop = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2RGB)
        else:
            crop = plate_crop
        return self._ocr.run_one(crop, return_confidence=True)

    def detect(self, frames: list[np.ndarray]) -> list[list[PlateDetection]]:
        if self._yolo is None or self._ocr is None:
            self.warmup()
        if not frames:
            return []

        # Ultralytics handles a list of frames as a true batch.
        try:
            yolo_results = self._yolo.predict(
                frames,
                conf=self._detector_conf,
                verbose=False,
                device=self._device,
            )
        except Exception:
            logger.exception("Keypoint detector inference failed")
            return [[] for _ in frames]

        out: list[list[PlateDetection]] = []
        for frame, result in zip(frames, yolo_results):
            frame_dets: list[PlateDetection] = []
            if result.boxes is None or len(result.boxes) == 0 or result.keypoints is None:
                out.append(frame_dets)
                continue

            boxes = result.boxes
            kpts = result.keypoints

            box_xyxy = boxes.xyxy.cpu().numpy()
            box_conf = boxes.conf.cpu().numpy()
            kp_xy = kpts.xy.cpu().numpy()
            kp_conf = kpts.conf.cpu().numpy() if kpts.conf is not None else None

            for i in range(len(boxes)):
                corners = kp_xy[i]
                if corners.shape[0] != 4:
                    continue

                if kp_conf is not None:
                    per_conf = kp_conf[i]
                    if np.any(per_conf < self._keypoint_conf):
                        continue
                    avg_kp_conf = float(np.mean(per_conf))
                    if avg_kp_conf < self._min_avg_keypoint_conf:
                        continue
                else:
                    avg_kp_conf = 0.0

                ordered, target_w, target_h, skew_ratio = self._quad_geometry(corners)

                # Drop heavily perspective-distorted plates — even after the
                # warp, the OCR struggles when the source is this skewed.
                if skew_ratio > self._max_skew_ratio:
                    logger.debug(
                        "Keypoint detection rejected: skew_ratio=%.2f > %.2f",
                        skew_ratio,
                        self._max_skew_ratio,
                    )
                    continue

                warp_w = max(target_w, float(self._warp_min_w))
                warp_h = max(target_h, float(self._warp_min_h))
                warped = self._warp_plate(frame, ordered, warp_w, warp_h)
                if warped is None:
                    continue

                try:
                    ocr_pred = self._run_ocr(warped)
                except Exception:
                    logger.exception("OCR failed on warped plate crop")
                    continue

                if ocr_pred is None or not getattr(ocr_pred, "plate", None):
                    continue
                text = ocr_pred.plate.strip().upper()
                if not text:
                    continue

                # OCR confidence handling matches the bbox detector.
                ocr_conf = 0.0
                char_probs = getattr(ocr_pred, "char_probs", None)
                if char_probs is not None:
                    probs = [float(x) for x in np.asarray(char_probs).tolist()]
                    non_pad = [p for p in probs if p > 0.0]
                    if non_pad:
                        ocr_conf = statistics.mean(non_pad)

                # Hard OCR-confidence gate — see fastalpr_detector for rationale.
                if ocr_conf < self._min_ocr_confidence:
                    continue

                x1, y1, x2, y2 = box_xyxy[i].tolist()
                det_conf = float(box_conf[i])
                combined = (det_conf + ocr_conf) / 2 if ocr_conf > 0 else det_conf

                region = getattr(ocr_pred, "region", None) or "unknown"

                ordered_corners: list[tuple[float, float]] = [
                    (float(pt[0]), float(pt[1])) for pt in ordered
                ]

                frame_dets.append(
                    PlateDetection(
                        plate_text=text,
                        bbox=BoundingBox(
                            x1=float(x1),
                            y1=float(y1),
                            x2=float(x2),
                            y2=float(y2),
                            confidence=det_conf,
                        ),
                        region_name=str(region),
                        confidence=combined,
                        frame_number=0,  # populated by caller
                        timestamp=0.0,   # populated by caller
                        ocr_confidence=ocr_conf,
                        corners=ordered_corners,
                    )
                )
            out.append(frame_dets)

        return out
