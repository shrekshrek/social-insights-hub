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

    # Database connection pool settings (optimized for AI tasks)
    DB_POOL_SIZE: int = 50
    DB_MAX_OVERFLOW: int = 100
    DB_POOL_TIMEOUT: int = 60
    DB_POOL_RECYCLE: int = 1800  # 30 minutes

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 10

    # Celery settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # ========== AI Service Configuration ==========
    # DeepSeek API Configuration
    DEEPSEEK_API_KEY: str | None = Field(
        default=None,
        description="DeepSeek API Key (required for AI features)"
    )
    DEEPSEEK_BASE_URL: str = Field(
        default="https://api.deepseek.com",
        description="DeepSeek API Base URL"
    )

    # DeepSeek Model Configuration
    DEEPSEEK_CHAT_MODEL: str = Field(
        default="deepseek-chat",
        description="Model for data processing tasks (screening, extraction)"
    )
    DEEPSEEK_CHAT_MAX_TOKENS: int = Field(
        default=8192,
        description="Max tokens for Chat model"
    )
    DEEPSEEK_REASONER_MODEL: str = Field(
        default="deepseek-reasoner",
        description="Model for complex analysis (clustering, competitive analysis)"
    )
    DEEPSEEK_REASONER_MAX_TOKENS: int = Field(
        default=65536,
        description="Max tokens for Reasoner model"
    )
    DEEPSEEK_TEMPERATURE: float = Field(
        default=0.0,
        description="Model temperature (0 = deterministic)"
    )

    # DeepSeek Pricing Configuration (CNY per million tokens)
    DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION: float = Field(
        default=2.0,
        description="Chat model input price: CNY/million tokens"
    )
    DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION: float = Field(
        default=3.0,
        description="Chat model output price: CNY/million tokens"
    )
    DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION: float = Field(
        default=2.0,
        description="Reasoner model input price: CNY/million tokens"
    )
    DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION: float = Field(
        default=3.0,
        description="Reasoner model output price: CNY/million tokens"
    )

    # ========== Celery Task Configuration ==========
    # AI Task Concurrency Configuration
    CELERY_AI_SCREENING_CONCURRENT_STREAMS: int = Field(
        default=100,
        description="Concurrent streams for AI screening tasks"
    )
    CELERY_AI_DEEP_ANALYSIS_CONCURRENCY: int = Field(
        default=100,
        description="Concurrent LLM calls for deep analysis"
    )
    CELERY_AI_POSTS_BATCH_SIZE: int = Field(
        default=5,
        description="Batch size for AI post processing"
    )
    CELERY_AI_COMMENTS_BATCH_SIZE: int = Field(
        default=10,
        description="Batch size for AI comment processing"
    )
    CELERY_TASK_MAX_ITEMS_LIMIT: int = Field(
        default=20000,
        description="Max items per Celery task"
    )
    CELERY_TASK_MAX_COMMENTS_PER_POST_FOR_DEEP_ANALYSIS: int = Field(
        default=50,
        description="Max comments per post for deep analysis"
    )

    # Database Batch Commit Configuration
    DB_COMMIT_AFTER_BATCH_COUNT: int = Field(
        default=20,
        description="Commit to DB after processing N batches"
    )

    # ========== Batch Analysis Framework Configuration ==========
    BATCH_ANALYSIS_DEFAULT_BATCH_SIZE: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Default batch size for global analysis"
    )
    BATCH_ANALYSIS_MIN_BATCH_SIZE: int = Field(
        default=20,
        ge=1,
        description="Minimum batch size"
    )
    BATCH_ANALYSIS_MAX_BATCH_SIZE: int = Field(
        default=40,
        ge=1,
        le=100,
        description="Maximum batch size"
    )
    BATCH_ANALYSIS_MAX_CONCURRENT_BATCHES: int = Field(
        default=100,
        ge=1,
        le=200,
        description="Maximum concurrent batches"
    )
    BATCH_ANALYSIS_CONCURRENT_TIMEOUT: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Concurrent processing timeout (seconds)"
    )
    BATCH_ANALYSIS_MAX_RETRIES: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Max retries on failure"
    )
    BATCH_ANALYSIS_ENABLE_CONCURRENT: bool = Field(
        default=True,
        description="Enable concurrent processing"
    )
    BATCH_ANALYSIS_ENABLE_BATCHING: bool = Field(
        default=True,
        description="Enable batch processing"
    )
    BATCH_ANALYSIS_ENABLE_DYNAMIC_SIZING: bool = Field(
        default=True,
        description="Enable dynamic batch size adjustment"
    )
    BATCH_ANALYSIS_LOG_TOKEN_USAGE: bool = Field(
        default=True,
        description="Log token usage for cost tracking"
    )

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

    # Model config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()


def get_settings() -> Settings:
    """
    获取应用配置实例

    Returns:
        Settings: 应用配置实例
    """
    return settings
