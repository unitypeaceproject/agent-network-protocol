"""Configuration management for ANP."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ANP configuration settings."""

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///anp.db",
        description="Database connection URL",
    )

    # API
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8080, description="API port")
    api_reload: bool = Field(default=False, description="Enable hot reload")

    # Identity
    identity_dir: Path = Field(
        default=Path.home() / ".anp",
        description="Directory for identity files",
    )

    # External services
    moltbook_api_url: str = Field(
        default="https://www.moltbook.com/api/v1",
        description="Moltbook API base URL",
    )
    moltbook_api_key: Optional[str] = Field(
        default=None,
        description="Moltbook API key for verification",
    )

    class Config:
        env_prefix = "ANP_"
        env_file = ".env"


settings = Settings()
