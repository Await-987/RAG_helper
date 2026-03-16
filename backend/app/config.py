"""
Configuration management for the FastAPI backend.
"""
import os
import uuid
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from storage_paths import (
    SHARED_STORAGE_ROOT as APP_SHARED_STORAGE_ROOT,
    STORED_FILES_DIR as APP_STORED_FILES_DIR,
    MINERU_OUTPUT_DIR as APP_MINERU_OUTPUT_DIR,
    AGENT_MEMORY_DIR as APP_AGENT_MEMORY_DIR,
    CHAT_SESSION_DIR as APP_CHAT_SESSION_DIR,
)

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
    AUTH_INSTANCE_ID: str = os.getenv("AUTH_INSTANCE_ID", uuid.uuid4().hex)

    # CORS settings
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Database settings
    COLLECTION_NAME: str = "database"
    QDRANT_MODE: str = os.getenv("QDRANT_MODE", "local")
    QDRANT_URL: Optional[str] = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
    QDRANT_LOCAL_PATH: str = os.getenv("QDRANT_LOCAL_PATH", "data/storages")
    QDRANT_LEXICAL_INDEX_DIR: str = os.getenv("QDRANT_LEXICAL_INDEX_DIR", "data/lex_index")
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    REDIS_PREFIX: str = os.getenv("REDIS_PREFIX", "rag")
    REDIS_SOCKET_TIMEOUT_SEC: int = int(os.getenv("REDIS_SOCKET_TIMEOUT_SEC", "5"))
    REDIS_SOCKET_CONNECT_TIMEOUT_SEC: int = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT_SEC", "5"))
    SHARED_STORAGE_ROOT: str = os.getenv("SHARED_STORAGE_ROOT", "data")

    # Storage paths
    STORAGE_ROOT: Path = APP_SHARED_STORAGE_ROOT
    STORAGE_DIR: Path = APP_STORED_FILES_DIR
    MINERU_OUTPUT_DIR: Path = APP_MINERU_OUTPUT_DIR
    AGENT_MEMORY_DIR: Path = APP_AGENT_MEMORY_DIR
    CHAT_SESSION_DIR: Path = APP_CHAT_SESSION_DIR

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

    # Agent memory settings
    AGENT_MEMORY_ENABLED: bool = os.getenv("AGENT_MEMORY_ENABLED", "true").lower() == "true"
    AGENT_MEMORY_TOKEN_LIMIT: int = int(os.getenv("AGENT_MEMORY_TOKEN_LIMIT", "12000"))
    AGENT_MEMORY_RETRIEVE_LIMIT: int = int(os.getenv("AGENT_MEMORY_RETRIEVE_LIMIT", "6"))
    AGENT_MEMORY_KEEP_RATE: float = float(os.getenv("AGENT_MEMORY_KEEP_RATE", "0.9"))
    MEMORY_TOKEN_COUNTER_MODEL: str = os.getenv("MEMORY_TOKEN_COUNTER_MODEL", "GPT_4O_MINI")
    CHAT_CONTEXT_BUDGET_LOG_ENABLED: bool = (
        os.getenv("CHAT_CONTEXT_BUDGET_LOG_ENABLED", "false").lower() == "true"
    )
    AGENT_COMPACT_ENABLED: bool = os.getenv("AGENT_COMPACT_ENABLED", "true").lower() == "true"
    AGENT_COMPACT_TRIGGER_MESSAGES: int = int(os.getenv("AGENT_COMPACT_TRIGGER_MESSAGES", "12"))
    AGENT_COMPACT_TRIGGER_CHARS: int = int(os.getenv("AGENT_COMPACT_TRIGGER_CHARS", "24000"))
    AGENT_COMPACT_KEEP_RECENT_MESSAGES: int = int(os.getenv("AGENT_COMPACT_KEEP_RECENT_MESSAGES", "4"))
    FACTUAL_EVIDENCE_MAX_CHARS: int = int(os.getenv("FACTUAL_EVIDENCE_MAX_CHARS", "6000"))

    # Table summary model settings
    TABLE_SUMMARY_MODEL_PATH: Optional[str] = os.getenv("TABLE_SUMMARY_MODEL_PATH")
    TABLE_SUMMARY_DEVICE: Optional[str] = os.getenv("TABLE_SUMMARY_DEVICE")

    class Config:
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()
