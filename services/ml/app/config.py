from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """ML service configuration. All values can be overridden via environment variables with ML_ prefix."""

    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_prefix="ML_",
        case_sensitive=False,
    )

    # --- Authentication ---
    api_key: str = "change-me"

    # --- Backend push target ---
    backend_url: str = "http://localhost:8001"
    backend_api_key: str = ""

    # --- fast-alpr settings ---
    fastalpr_detector_model: str = "yolo-v9-s-608-license-plate-end2end"
    fastalpr_detector_model_path: str = ""  # local ONNX detector path (overrides hub model when set)
    fastalpr_detector_conf: float = 0.4
    fastalpr_ocr_model: str = ""  # hub model name (leave empty when using custom paths)
    fastalpr_ocr_model_path: str = "models/ru_ocr.onnx"  # custom ONNX model
    fastalpr_ocr_config_path: str = "models/ru_plate_config.yaml"  # custom plate config

    # --- Video processing ---
    frame_skip: int = 5          # process every Nth frame
    batch_size: int = 4          # frames per detector call

    # --- Filtering ---
    min_bbox_area_pct: float = 0.10  # minimum bbox area as % of frame area

    # --- Plate tracker ---
    tracker_window_sec: float = 10.0    # deduplication sliding window
    tracker_min_confirmations: int = 3  # min detections to confirm a plate
    tracker_departure_sec: float = 5.0  # seconds without detection → "departed"
    tracker_max_text_distance: int = 1  # strict match by OCR text distance
    tracker_spatial_match_iou: float = 0.45  # fallback IoU match for OCR variants
    tracker_spatial_match_window_sec: float = 1.5  # recency window for IoU fallback
    tracker_max_spatial_text_distance: int = 10  # max OCR distance in IoU fallback (effectively disabled for normal plates)
    tracker_spatial_match_center_distance_factor: float = 2.5  # fallback center-distance match for moving plates
    tracker_duplicate_event_iou: float = 0.35  # suppress near-duplicate confirmed events by IoU
    tracker_duplicate_event_window_sec: float = 4.0  # time window for duplicate suppression
    tracker_duplicate_event_text_distance: int = 2  # OCR distance for duplicate suppression
    tracker_duplicate_event_center_distance_factor: float = 3.0  # duplicate suppression by center-distance

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Default camera (auto-start on boot) ---
    default_source: str | None = None
    default_camera_role: str = "entry"
    auto_start: bool = False

    @property
    def resolved_default_source(self) -> str | None:
        if not self.default_source:
            return None
        if "://" in self.default_source:
            return self.default_source

        source_path = Path(self.default_source)
        if source_path.is_absolute():
            return str(source_path)
        return str((SERVICE_ROOT / source_path).resolve())


settings = Settings()
