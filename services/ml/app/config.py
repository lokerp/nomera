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

    # --- Video processing ---
    frame_skip: int = 5          # process every Nth frame
    batch_size: int = 4          # frames per detector call

    # --- Filtering ---
    min_bbox_area_pct: float = 0.10  # minimum bbox area as % of frame area

    # --- Plate tracker ---
    tracker_window_sec: float = 10.0    # deduplication sliding window
    tracker_min_confirmations: int = 3  # min detections to confirm a plate
    tracker_departure_sec: float = 5.0  # seconds without detection → "departed"

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
