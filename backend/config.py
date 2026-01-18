import json
import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    rtsp_url_high: str = Field(default="rtsp://192.168.1.137/streamtype=0")
    rtsp_url_low: str = Field(default="rtsp://192.168.1.137/streamtype=1")
    openrouter_api_key: str = Field(default="")
    openrouter_model: str = Field(default="google/gemma-3-4b-it:free")
    openrouter_daily_limit: int = Field(default=1000)
    openrouter_min_interval_seconds: int = Field(default=30)
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    data_dir: Path = Field(default=Path("./data"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class RuntimeSettings:
    """Runtime settings that can be changed without restart."""

    _instance: Optional["RuntimeSettings"] = None
    _settings_file: Path

    def __init__(self, settings_file: Path):
        self._settings_file = settings_file
        self._load()

    @classmethod
    def get_instance(cls, settings_file: Optional[Path] = None) -> "RuntimeSettings":
        if cls._instance is None:
            if settings_file is None:
                settings_file = Path("config/settings.json")
            cls._instance = cls(settings_file)
        return cls._instance

    def _load(self):
        if self._settings_file.exists():
            with open(self._settings_file, "r") as f:
                data = json.load(f)
        else:
            data = {}

        self.telegram_enabled: bool = data.get("telegram_enabled", True)
        self.telegram_screenshot: bool = data.get("telegram_screenshot", True)
        self.telegram_gif: bool = data.get("telegram_gif", True)
        self.detection_threshold: int = data.get("detection_threshold", 50)
        self.retention_hours: int = data.get("retention_hours", 48)
        self.theme: str = data.get("theme", "dark")
        self.notification_cooldown_seconds: int = data.get("notification_cooldown_seconds", 60)

    def save(self):
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._settings_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_dict(self) -> dict:
        return {
            "telegram_enabled": self.telegram_enabled,
            "telegram_screenshot": self.telegram_screenshot,
            "telegram_gif": self.telegram_gif,
            "detection_threshold": self.detection_threshold,
            "retention_hours": self.retention_hours,
            "theme": self.theme,
            "notification_cooldown_seconds": self.notification_cooldown_seconds,
        }

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.save()


# Global instances
settings = Settings()
runtime_settings = RuntimeSettings.get_instance(Path("config/settings.json"))
