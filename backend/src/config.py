from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List


class Settings(BaseSettings):
    """
    Global settings for the application.
    Loaded from environment variables and/or a .env file.
    """

    # Environment settings
    ENVIRONMENT: str = "development"

    # Database settings
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost/dbname"

    # Database connection pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600  # 1 hour

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 10

    # Celery settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Signing strategy settings
    SIGNING_STRATEGY: str = "javascript"
    SIGNING_JS_BUNDLE: str | None = None
    SIGNING_PLAYWRIGHT_BROWSER: str = "chromium"
    SIGNING_PLAYWRIGHT_HEADLESS: bool = True
    SIGNING_PLAYWRIGHT_USER_DATA_DIR: str | None = None
    SIGNING_PLAYWRIGHT_STEALTH_JS: str | None = None
    SIGNING_PLAYWRIGHT_DEFAULT_COOKIES: str | None = None

    # Sign Service settings (MediaCrawlerPro-SignSrv)
    SIGN_SERVICE_ENABLED: bool = True
    SIGN_SERVICE_HOST: str = "localhost"
    SIGN_SERVICE_PORT: int = 8989

    # API settings
    API_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Full-Stack Starter API"
    VERSION: str = "0.1.0"

    # CORS settings
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )

    # Auth settings
    SECRET_KEY: str = Field(
        default="a_very_secret_key_for_development_only_change_in_production",
        min_length=32,
        description="Secret key for JWT encoding",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    PASSWORD_MIN_LENGTH: int = 8

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate that SECRET_KEY is secure in production"""
        if "development_only" in v:
            import os

            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError(
                    "请设置一个安全的 SECRET_KEY！可以使用以下命令生成: "
                    "openssl rand -hex 32"
                )
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v

    @field_validator("SIGNING_STRATEGY")
    @classmethod
    def validate_signing_strategy(cls, v: str) -> str:
        allowed = {"javascript", "playwright"}
        value = v.lower()
        if value not in allowed:
            raise ValueError(f"SIGNING_STRATEGY 必须是 {allowed} 之一")
        return value

    # Model config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
