"""
Authentication service.
Wraps the existing UserAuth from tools.user_auth.
"""
import sys
from pathlib import Path
from datetime import timedelta
from typing import Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.user_auth import UserAuth, UserRole
from app.core.security import create_access_token, verify_password, get_password_hash
from app.config import settings


class AuthService:
    """Authentication service wrapping UserAuth"""

    def __init__(self):
        self.user_auth = UserAuth()

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """
        Authenticate user and return user info.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User info dict if authenticated, None otherwise
        """
        return self.user_auth.authenticate(username, password)

    def login(self, username: str, password: str) -> Tuple[Optional[str], Optional[dict], Optional[str]]:
        """
        Login user and return JWT token.

        Args:
            username: Username
            password: Plain text password

        Returns:
            Tuple of (token, user_info, error_message)
        """
        user = self.authenticate(username, password)

        if user is None:
            return None, None, "Invalid username or password"

        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["username"], "role": user["role"]},
            expires_delta=access_token_expires
        )

        return access_token, user, None

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """
        Get user by username.

        Args:
            username: Username

        Returns:
            User info dict if found, None otherwise
        """
        all_users = self.user_auth.get_all_users()
        for user in all_users:
            if user["username"] == username:
                return user
        return None

    def is_admin(self, username: str) -> bool:
        """Check if user is admin"""
        user = self.get_user_by_username(username)
        return user is not None and user.get("role") == UserRole.ADMIN
