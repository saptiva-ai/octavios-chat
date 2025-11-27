"""
BankAdvisor Configuration Module

Loads configuration from environment variables with sensible defaults.
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    log_level: str = "INFO"

    # Database Configuration (PostgreSQL)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "octavios"
    postgres_password: str = "secure_postgres_password"
    postgres_db: str = "bankadvisor"

    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct sync PostgreSQL URL for pandas/ETL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
