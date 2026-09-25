import os
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class Settings:
    """Application settings with environment variable discovery and sensitive masking."""
    
    # Environment & Info
    APP_ENV: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    PROJECT_NAME: str = field(default_factory=lambda: os.getenv("PROJECT_NAME", "Universal Options Market Dashboard"))
    API_V1_PREFIX: str = field(default_factory=lambda: os.getenv("API_V1_PREFIX", "/api/v1"))
    BACKEND_HOST: str = field(default_factory=lambda: os.getenv("BACKEND_HOST", "0.0.0.0"))
    BACKEND_PORT: int = field(default_factory=lambda: int(os.getenv("BACKEND_PORT", "8000")))
    TIMEZONE: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Kolkata"))
    
    # Snapshot Engine & Workers
    SNAPSHOT_INTERVAL_SECONDS: int = field(default_factory=lambda: int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "5")))
    MARKET_DATA_REFRESH_RATE_MS: int = field(default_factory=lambda: int(os.getenv("MARKET_DATA_REFRESH_RATE_MS", "1000")))
    
    # PostgreSQL Database
    POSTGRES_SERVER: str = field(default_factory=lambda: os.getenv("POSTGRES_SERVER", "localhost"))
    POSTGRES_PORT: int = field(default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432")))
    POSTGRES_DB: str = field(default_factory=lambda: os.getenv("POSTGRES_DB", "options_market_db"))
    POSTGRES_USER: str = field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres"))
    POSTGRES_PASSWORD: str = field(default_factory=lambda: os.getenv("POSTGRES_PASSWORD", "postgres_secure_password"))
    POSTGRES_POOL_SIZE: int = field(default_factory=lambda: int(os.getenv("POSTGRES_POOL_SIZE", "10")))
    POSTGRES_MAX_OVERFLOW: int = field(default_factory=lambda: int(os.getenv("POSTGRES_MAX_OVERFLOW", "20")))

    # Redis Cache & State
    REDIS_HOST: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    REDIS_PORT: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    REDIS_PASSWORD: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", None))
    REDIS_DB: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    REDIS_TIMEOUT_MS: int = field(default_factory=lambda: int(os.getenv("REDIS_TIMEOUT_MS", "2000")))

    # Angel One SmartAPI Credentials (NEVER logged or exposed)
    ANGEL_API_KEY: Optional[str] = field(default_factory=lambda: os.getenv("ANGEL_API_KEY", "vTz0rnxJ"))
    ANGEL_CLIENT_CODE: Optional[str] = field(default_factory=lambda: os.getenv("ANGEL_CLIENT_CODE", "A700031"))
    ANGEL_PASSWORD: Optional[str] = field(default_factory=lambda: os.getenv("ANGEL_PASSWORD", "1811"))
    ANGEL_TOTP_SECRET: Optional[str] = field(default_factory=lambda: os.getenv("ANGEL_TOTP_SECRET", "ABZDZPRGOK7SGZIS52GXKHZR5M"))
    
    # Google Sheets Integration
    GOOGLE_SERVICE_ACCOUNT_EMAIL: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", None))
    GOOGLE_SHEET_ID: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", None))

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Construct PostgreSQL SQLAlchemy URI."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def async_database_uri(self) -> str:
        """Construct Async PostgreSQL SQLAlchemy URI for high-throughput snapshot ingestion."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        """Construct Redis URI."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def get_masked_summary(self) -> dict:
        """Safe dictionary representation guaranteed not to expose secrets."""
        return {
            "app_env": self.APP_ENV,
            "project_name": self.PROJECT_NAME,
            "api_v1_prefix": self.API_V1_PREFIX,
            "timezone": self.TIMEZONE,
            "snapshot_interval_seconds": self.SNAPSHOT_INTERVAL_SECONDS,
            "postgres": {
                "server": self.POSTGRES_SERVER,
                "port": self.POSTGRES_PORT,
                "database": self.POSTGRES_DB,
                "user": self.POSTGRES_USER,
            },
            "redis": {
                "host": self.REDIS_HOST,
                "port": self.REDIS_PORT,
                "db": self.REDIS_DB,
                "auth_configured": bool(self.REDIS_PASSWORD),
            },
            "angel_one": {
                "client_code_configured": bool(self.ANGEL_CLIENT_CODE),
                "api_key_configured": bool(self.ANGEL_API_KEY),
                "totp_configured": bool(self.ANGEL_TOTP_SECRET),
            },
            "google_sheets": {
                "service_account_configured": bool(self.GOOGLE_SERVICE_ACCOUNT_EMAIL),
                "sheet_id_configured": bool(self.GOOGLE_SHEET_ID),
            }
        }


settings = Settings()
