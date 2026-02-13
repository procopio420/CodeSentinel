from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MONGODB_URI: str = "mongodb://localhost:27017"
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"

    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    RATE_LIMIT_REDIS_URL: str = "redis://localhost:6379/1"
    RATE_LIMIT_PER_HOUR: int = 10
    TRUSTED_PROXY_HEADERS: bool = False

    CACHE_ENABLED: bool = True
    CACHE_REDIS_URL: str = "redis://localhost:6379/2"
    CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 30
    CACHE_PREFIX: str = "acrev:"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
