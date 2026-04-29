from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        case_sensitive=False,
    )

    backend_api_key: str = "dev-backend-key"
    ml_url: str = "http://localhost:8000"
    ml_api_key: str = "dev-secret-key"
    video_path: str = str((SERVICE_ROOT.parent / "ml" / "example_video.mp4").resolve())
    host: str = "0.0.0.0"
    port: int = 8001

    @property
    def resolved_video_path(self) -> str:
        path = Path(self.video_path)
        if path.is_absolute():
            return str(path)
        return str((SERVICE_ROOT / path).resolve())


settings = Settings()
