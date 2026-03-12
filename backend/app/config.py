"""
Configuration management for the FastAPI backend.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings"""

    # API settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "RAG Backend API"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # JWT settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # CORS settings
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Database settings
    COLLECTION_NAME: str = "database"

    # Storage paths
    STORAGE_DIR: Path = PROJECT_ROOT / "data" / "stored_files"
    MINERU_OUTPUT_DIR: Path = PROJECT_ROOT / "data" / "mineru_output"

    # Model settings (from environment)
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_API_URL: Optional[str] = os.getenv("url")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "qwq32b")

    # Embedding model settings
    EMBEDDING_MODEL_PATH: Optional[str] = os.getenv("conan_path")
    EMBEDDING_DEVICE: Optional[str] = os.getenv("EMBEDDING_DEVICE")

    # Reranker settings
    RERANKER_PATH: Optional[str] = os.getenv("reranker_path")
    RERANKER_DEVICE: Optional[str] = os.getenv("RERANKER_DEVICE")

    # Table summary model settings
    TABLE_SUMMARY_MODEL_PATH: Optional[str] = os.getenv("TABLE_SUMMARY_MODEL_PATH")
    TABLE_SUMMARY_DEVICE: Optional[str] = os.getenv("TABLE_SUMMARY_DEVICE")

    class Config:
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()
