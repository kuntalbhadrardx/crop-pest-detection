"""Application configuration loaded from environment variables / .env file."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (parent of app/).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings. Every field can be overridden via an env var or .env.

    Field names map to UPPERCASE env vars automatically
    (e.g. ``model_path`` <-> ``MODEL_PATH``).
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Model ---------------------------------------------------------
    model_path: Path = BASE_DIR / "models" / "custom.pt"
    fallback_model: str = "yolov8n.pt"
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.45
    image_size: int = 640
    device: str = ""  # "" = auto (CUDA if available, else CPU)

    # --- Storage -------------------------------------------------------
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'scans.db').as_posix()}"
    upload_dir: Path = BASE_DIR / "uploads"
    max_upload_mb: int = 20

    # --- Behaviour -----------------------------------------------------
    # Classes that never count as "affected" (e.g. "healthy" leaves).
    healthy_classes: list[str] = []
    cors_origins: list[str] = ["*"]

    # --- Weather / risk forecasting --------------------------------------
    # Provider is swappable so a future offline source (manual entry, sensors)
    # can replace open-meteo without touching the risk engine.
    weather_provider: str = "open-meteo"
    weather_cache_ttl_hours: int = 24
    weather_cache_path: Path = BASE_DIR / "data" / "weather_cache.json"

    # --- Dataset downloads (training only) ------------------------------
    roboflow_api_key: str = ""

    @field_validator("model_path", "upload_dir", "weather_cache_path", mode="before")
    @classmethod
    def _resolve_relative_paths(cls, value: Path | str) -> Path:
        """Resolve path settings that point outside/relative to the project root."""
        path = Path(value)
        return path if path.is_absolute() else BASE_DIR / path


settings = Settings()
