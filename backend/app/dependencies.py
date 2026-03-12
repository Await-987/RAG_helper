"""
Dependency injection for the FastAPI backend.
Provides cached model instances and services.
"""
import os
import sys
from pathlib import Path
from functools import lru_cache
from typing import Optional, Generator

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.core.security import verify_token
# Lazy import services to avoid circular imports
# from app.services import AuthService, ChatService, FileService, UserService
from tools.user_auth import UserRole

# Security scheme
security = HTTPBearer()


# ==================== Model Caching (without Streamlit) ====================

_embedding_model_cache = None
_reranker_model_cache = None
_database_toolkit_cache = None
_table_summary_model_cache = None
_table_summary_tokenizer_cache = None


def get_embedding_model():
    """
    Get cached embedding model (using module-level cache instead of @st.cache_resource)
    """
    global _embedding_model_cache

    if _embedding_model_cache is not None:
        return _embedding_model_cache

    from camel.embeddings import SentenceTransformerEncoder

    path = settings.EMBEDDING_MODEL_PATH
    if not path:
        raise ValueError("Missing env var `conan_path` for local embedding model path")

    full_path = os.path.join(PROJECT_ROOT, path)
    print(f"Loading embedding model from: {full_path}")

    # Auto-detect device
    device = settings.EMBEDDING_DEVICE
    if device is None:
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    print(f"  Using device: {device}")

    _embedding_model_cache = SentenceTransformerEncoder(
        model_name=str(full_path),
        device=device,
        trust_remote_code=True,
    )

    print("  Embedding model loaded successfully!")
    return _embedding_model_cache


def get_reranker_model():
    """
    Get cached reranker model (optional)
    """
    global _reranker_model_cache

    if _reranker_model_cache is not None:
        return _reranker_model_cache

    if not settings.RERANKER_PATH:
        return None

    try:
        from sentence_transformers import CrossEncoder

        full_path = os.path.join(PROJECT_ROOT, settings.RERANKER_PATH)
        print(f"Loading reranker model from: {full_path}")

        device = settings.RERANKER_DEVICE
        if device is None:
            import torch
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

        print(f"  Using device: {device}")
        _reranker_model_cache = CrossEncoder(full_path, device=device)
        print("  Reranker model loaded successfully!")

    except Exception as e:
        print(f"Failed to load reranker: {e}")
        _reranker_model_cache = None

    return _reranker_model_cache


def get_database_toolkit():
    """
    Get cached DatabaseToolkit instance (shared across sessions)
    """
    global _database_toolkit_cache

    if _database_toolkit_cache is not None:
        return _database_toolkit_cache

    from tools import DatabaseToolkit

    print("Initializing DatabaseToolkit...")
    _database_toolkit_cache = DatabaseToolkit()
    # Warmup lexical index
    _database_toolkit_cache.warmup_lexical_index()
    print("  DatabaseToolkit initialized!")

    return _database_toolkit_cache


def init_table_summary_model():
    """
    Initialize table summary model (local deployment)
    """
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is not None:
        return True

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = settings.TABLE_SUMMARY_MODEL_PATH
        if not model_path:
            return False

        full_path = os.path.join(PROJECT_ROOT, model_path)

        if not os.path.exists(full_path):
            print(f"[WARNING] Table summary model not found: {full_path}")
            return False

        print(f"Loading table summary model: {full_path}")

        device = settings.TABLE_SUMMARY_DEVICE
        if device is None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'

        print(f"  Using device: {device}")

        _table_summary_tokenizer_cache = AutoTokenizer.from_pretrained(
            full_path,
            trust_remote_code=True
        )

        _table_summary_model_cache = AutoModelForCausalLM.from_pretrained(
            full_path,
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
            device_map=device,
            trust_remote_code=True
        )
        _table_summary_model_cache.eval()

        print("  Table summary model loaded successfully!")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to load table summary model: {e}")
        _table_summary_model_cache = None
        _table_summary_tokenizer_cache = None
        return False


def get_table_summary_model():
    """
    Get table summary model and tokenizer
    """
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is None:
        init_table_summary_model()

    return _table_summary_model_cache, _table_summary_tokenizer_cache


def cleanup_table_summary_model():
    """Cleanup table summary model to free GPU memory"""
    global _table_summary_model_cache, _table_summary_tokenizer_cache

    if _table_summary_model_cache is None:
        return

    import torch
    import gc

    try:
        _table_summary_model_cache = _table_summary_model_cache.to('cpu')
        del _table_summary_model_cache
    except Exception:
        pass

    _table_summary_model_cache = None
    _table_summary_tokenizer_cache = None

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    print("[INFO] Table summary model released")


# ==================== Service Dependencies ====================
# Using lazy imports to avoid circular dependency with services module

@lru_cache(maxsize=1)
def get_auth_service():
    """Get cached AuthService instance"""
    from app.services.auth_service import AuthService
    return AuthService()


@lru_cache(maxsize=1)
def get_chat_service():
    """Get cached ChatService instance"""
    from app.services.chat_service import ChatService
    return ChatService()


@lru_cache(maxsize=1)
def get_file_service():
    """Get cached FileService instance"""
    from app.services.file_service import FileService
    return FileService()


@lru_cache(maxsize=1)
def get_user_service():
    """Get cached UserService instance"""
    from app.services.user_service import UserService
    return UserService()


# ==================== Authentication Dependencies ====================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Get current user from JWT token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    # Verify user exists
    auth_service = get_auth_service()
    user = auth_service.get_user_by_username(username)

    if user is None:
        raise credentials_exception

    return user


async def get_current_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get current user and verify admin role
    """
    if current_user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[dict]:
    """
    Get current user if authenticated, otherwise return None
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        return None

    username: str = payload.get("sub")
    if username is None:
        return None

    auth_service = get_auth_service()
    user = auth_service.get_user_by_username(username)

    return user
