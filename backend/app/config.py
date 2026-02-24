from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/supply_planning"
    environment: str = "dev"  # dev, local, prod
    dev_default_user_email: str | None = None  # Fallback when X-Dev-User not provided (dev/local only)

    class Config:
        env_file = ".env"


settings: Settings = Settings()
