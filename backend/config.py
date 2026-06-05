from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional, List
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Settings
    database_url: str = "sqlite:///./data/posted.db"
    dev_mode: bool = False
    
    # Target Site configuration for asset syncing
    target_host: str = "https://caarms.princeton.edu"
    bypass_header_name: str = "x-wdsoit-bot-bypass"
    bypass_header_value: str = "true"
    
    # Webhook Security
    drupal_webhook_token: str = "secret_drupal_token"
    nametags_webhook_token: str = "secret_nametags_token"
    allowed_admin_principals: str = "bino@princeton.edu"

    @model_validator(mode="after")
    def validate_urls(self) -> "Settings":
        from urllib.parse import urlparse
        import logging
        logger = logging.getLogger("posted.config")

        result = urlparse(self.target_host)
        if not all([result.scheme, result.netloc]):
            logger.error(f"Configuration Error: target_host has an invalid URL: {self.target_host}")
            raise ValueError(f"target_host has an invalid URL: {self.target_host}")
        return self

settings = Settings()
