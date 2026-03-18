"""
Dependency injection for the FastAPI backend.
Provides cached runtime instances and services.
"""
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

from app.core.security import verify_token
from app.core.model_runtime import (
    cleanup_table_summary_model,
    get_embedding_model,
    get_reranker_model,
    get_table_summary_model,
    init_table_summary_model,
)
# Lazy import services to avoid circular imports
# from app.services import AuthService, ChatService, FileService, UserService
from tools.user_auth import UserRole

# Security scheme
security = HTTPBearer()


_database_toolkit_cache = None
# ==================== Runtime Caching ====================


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
    print("  DatabaseToolkit initialized!")

    return _database_toolkit_cache


def init_backend_startup() -> None:
    """
    Initialize backend resources during FastAPI startup.

    This eagerly warms up components that are otherwise initialized on first
    request, reducing latency for file management and lexical retrieval.
    """
    print("[STARTUP] Initializing backend resources...")

    file_service = get_file_service()
    database_toolkit = get_database_toolkit()

    print("[STARTUP] Warming up lexical index and reranker...")
    database_toolkit.warmup_lexical_index()

    print("[STARTUP] Warming up file management...")
    file_service.warmup()

    print("[STARTUP] Backend resources ready")


def cleanup_database_toolkit():
    """Close the shared DatabaseToolkit instance if it was initialized."""
    global _database_toolkit_cache

    if _database_toolkit_cache is None:
        return

    try:
        _database_toolkit_cache.close()
    except Exception as e:
        print(f"[WARNING] Failed to close DatabaseToolkit: {e}")
    finally:
        _database_toolkit_cache = None


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
