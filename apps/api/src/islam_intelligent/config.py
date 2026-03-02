"""Application configuration scaffold."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "Islam Intelligent API"
    environment: str = "development"


settings = Settings()
