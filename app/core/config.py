from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "AuditorIA External API Service"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # S3 / MinIO
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_ACCESS_KEY: Optional[str] = None
    MINIO_URL: Optional[str] = None
    S3_BUCKET: str = "audios"
    S3_EXTERNAL_ENDPOINT: str = "http://localhost:9000"

    # Security
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: set = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
    CORS_ORIGINS: list[str] = ["*"]

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings():
    return Settings()
