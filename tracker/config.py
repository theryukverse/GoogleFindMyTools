import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DATA_DIR: str = os.getenv("DATA_DIR", "/data")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "")
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
    LOCATION_PROVIDER: str = os.getenv("LOCATION_PROVIDER", "google_find_my")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    TILE_URL: str = os.getenv(
        "TILE_URL", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    )
    TILE_ATTRIBUTION: str = os.getenv(
        "TILE_ATTRIBUTION",
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def get_database_path(self) -> str:
        """Returns the resolved database path, creating parent directories if needed."""
        if self.DATABASE_PATH:
            db_path = Path(self.DATABASE_PATH)
        else:
            # Check if /data is writable; if not (e.g. running locally without root), fallback to ./data
            data_dir = Path(self.DATA_DIR)
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                data_dir = Path("./data")
                data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "tracker.db"

        # Ensure directory exists
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            pass

        return str(db_path)


settings = Settings()
