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


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() == "true"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


class Settings(BaseSettings):
    """Application settings"""

    # API settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "RAG Backend API"
    DEBUG: bool = _env_bool("DEBUG", False)

    # JWT settings
    SECRET_KEY: str = _env_str("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    AUTH_INSTANCE_ID: str = _env_str("AUTH_INSTANCE_ID", uuid.uuid4().hex)

    # RAG API Key for external service access
    RAG_API_KEY: str = _env_str("RAG_API_KEY", "")

    # CORS settings
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Database settings
    COLLECTION_NAME: str = "database"
    QDRANT_MODE: str = _env_str("QDRANT_MODE", "local")
    QDRANT_URL: Optional[str] = _env_str("QDRANT_URL")
    QDRANT_API_KEY: Optional[str] = _env_str("QDRANT_API_KEY")
    QDRANT_LOCAL_PATH: str = _env_str("QDRANT_LOCAL_PATH", "data/storages")
    QDRANT_LEXICAL_INDEX_DIR: str = _env_str("QDRANT_LEXICAL_INDEX_DIR", "data/lex_index")
    REDIS_URL: Optional[str] = _env_str("REDIS_URL")
    REDIS_PREFIX: str = _env_str("REDIS_PREFIX", "rag")
    REDIS_SOCKET_TIMEOUT_SEC: int = _env_int("REDIS_SOCKET_TIMEOUT_SEC", 5)
    REDIS_SOCKET_CONNECT_TIMEOUT_SEC: int = _env_int("REDIS_SOCKET_CONNECT_TIMEOUT_SEC", 5)
    SHARED_STORAGE_ROOT: str = _env_str("SHARED_STORAGE_ROOT", "data")

    # Storage paths
    STORAGE_ROOT: Path = APP_SHARED_STORAGE_ROOT
    STORAGE_DIR: Path = APP_STORED_FILES_DIR
    MINERU_OUTPUT_DIR: Path = APP_MINERU_OUTPUT_DIR
    AGENT_MEMORY_DIR: Path = APP_AGENT_MEMORY_DIR
    CHAT_SESSION_DIR: Path = APP_CHAT_SESSION_DIR

    # Model settings (from environment)
    OPENAI_API_KEY: Optional[str] = _env_str("OPENAI_API_KEY")
    OPENAI_API_URL: Optional[str] = _env_str("url")
    MODEL_NAME: str = _env_str("MODEL_NAME", "qwq32b")

    # Main answer agent settings
    MAIN_AGENT_API_KEY: Optional[str] = _env_str("MAIN_AGENT_API_KEY") or OPENAI_API_KEY
    MAIN_AGENT_API_URL: Optional[str] = _env_str("MAIN_AGENT_API_URL") or OPENAI_API_URL
    MAIN_AGENT_MODEL_NAME: str = _env_str("MAIN_AGENT_MODEL_NAME", MODEL_NAME)
    MAIN_AGENT_TEMPERATURE: float = _env_float("MAIN_AGENT_TEMPERATURE", 0.2)
    MAIN_AGENT_TOP_P: float = _env_float("MAIN_AGENT_TOP_P", 0.9)
    MAIN_AGENT_MAX_TOKENS: int = _env_int("MAIN_AGENT_MAX_TOKENS", 4000)
    MAIN_AGENT_MESSAGE_WINDOW_SIZE: int = _env_int("MAIN_AGENT_MESSAGE_WINDOW_SIZE", 12)
    MAIN_AGENT_SUMMARIZE_THRESHOLD: int = _env_int("MAIN_AGENT_SUMMARIZE_THRESHOLD", 20)
    MAIN_AGENT_PRUNE_TOOL_CALLS: bool = _env_bool("MAIN_AGENT_PRUNE_TOOL_CALLS", True)
    MAIN_AGENT_STREAM_ACCUMULATE: bool = _env_bool("MAIN_AGENT_STREAM_ACCUMULATE", False)
    MAIN_AGENT_SYSTEM_PROMPT_PATH: Optional[str] = _env_str(
        "MAIN_AGENT_SYSTEM_PROMPT_PATH",
        "config/prompts/main_agent_system.txt",
    )

    # Helper agent settings
    INTENT_ROUTER_MODEL_NAME: str = _env_str("INTENT_ROUTER_MODEL_NAME", MODEL_NAME)
    INTENT_ROUTER_TEMPERATURE: float = _env_float("INTENT_ROUTER_TEMPERATURE", 0.0)
    INTENT_ROUTER_TOP_P: float = _env_float("INTENT_ROUTER_TOP_P", 1.0)
    INTENT_ROUTER_MAX_TOKENS: int = _env_int("INTENT_ROUTER_MAX_TOKENS", 800)

    SEARCH_REWRITER_MODEL_NAME: str = _env_str("SEARCH_REWRITER_MODEL_NAME", MODEL_NAME)
    SEARCH_REWRITER_TEMPERATURE: float = _env_float("SEARCH_REWRITER_TEMPERATURE", 0.1)
    SEARCH_REWRITER_TOP_P: float = _env_float("SEARCH_REWRITER_TOP_P", 1.0)
    SEARCH_REWRITER_MAX_TOKENS: int = _env_int("SEARCH_REWRITER_MAX_TOKENS", 1200)

    # Embedding model settings
    EMBEDDING_MODEL_PATH: Optional[str] = _env_str("conan_path")
    EMBEDDING_DEVICE: Optional[str] = _env_str("EMBEDDING_DEVICE")

    # Reranker settings
    RERANKER_PATH: Optional[str] = _env_str("reranker_path")
    RERANKER_DEVICE: Optional[str] = _env_str("RERANKER_DEVICE")

    # Agent memory settings
    AGENT_MEMORY_ENABLED: bool = _env_bool("AGENT_MEMORY_ENABLED", True)
    AGENT_MEMORY_TOKEN_LIMIT: int = _env_int("AGENT_MEMORY_TOKEN_LIMIT", 12000)
    AGENT_MEMORY_RETRIEVE_LIMIT: int = _env_int("AGENT_MEMORY_RETRIEVE_LIMIT", 6)
    AGENT_MEMORY_KEEP_RATE: float = _env_float("AGENT_MEMORY_KEEP_RATE", 0.9)
    MEMORY_TOKEN_COUNTER_MODEL: str = _env_str("MEMORY_TOKEN_COUNTER_MODEL", "GPT_4O_MINI")
    CHAT_CONTEXT_BUDGET_LOG_ENABLED: bool = _env_bool("CHAT_CONTEXT_BUDGET_LOG_ENABLED", False)
    AGENT_COMPACT_ENABLED: bool = _env_bool("AGENT_COMPACT_ENABLED", True)
    AGENT_COMPACT_TRIGGER_MESSAGES: int = _env_int("AGENT_COMPACT_TRIGGER_MESSAGES", 12)
    AGENT_COMPACT_TRIGGER_CHARS: int = _env_int("AGENT_COMPACT_TRIGGER_CHARS", 24000)
    AGENT_COMPACT_KEEP_RECENT_MESSAGES: int = _env_int("AGENT_COMPACT_KEEP_RECENT_MESSAGES", 4)
    FACTUAL_EVIDENCE_MAX_CHARS: int = _env_int("FACTUAL_EVIDENCE_MAX_CHARS", 6000)

    # Table summary model settings
    TABLE_SUMMARY_MODEL_PATH: Optional[str] = _env_str("TABLE_SUMMARY_MODEL_PATH")
    TABLE_SUMMARY_DEVICE: Optional[str] = _env_str("TABLE_SUMMARY_DEVICE")

    class Config:
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()
