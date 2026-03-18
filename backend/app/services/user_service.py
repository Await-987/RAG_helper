"""
User management service.
"""
import re
import shutil
from typing import List, Tuple, Optional
from loguru import logger

from tools.user_auth import UserAuth, UserRole
from app.config import settings
from app.schemas.user import User, UserCreate, UserResponse, UserListResponse


class UserService:
    """User management service"""

    def __init__(self):
        self.user_auth = UserAuth()

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "")
        return sanitized or "unknown"

    def _cleanup_user_runtime_data(self, username: str) -> None:
        """
        Remove persisted chat artifacts and in-memory sessions for a deleted user.
        """
        safe_username = self._sanitize_path_component(username)

        for root_dir in (settings.AGENT_MEMORY_DIR, settings.CHAT_SESSION_DIR):
            user_dir = root_dir / safe_username
            if user_dir.exists():
                shutil.rmtree(user_dir, ignore_errors=True)
                logger.info(f"已清理用户运行时数据目录: {user_dir}")

        try:
            from app.dependencies import get_chat_service

            chat_service = get_chat_service()
            session_ids = chat_service.session_manager.list_session_ids_for_user(username)
            for session_id in session_ids:
                chat_service.session_manager.clear_session(username, session_id)
            if session_ids:
                logger.info(f"已清理用户活跃会话: {username}, 共 {len(session_ids)} 个")
        except Exception as exc:
            logger.warning(f"清理用户活跃会话失败 {username}: {exc}")

    def get_all_users(self) -> UserListResponse:
        """
        Get all users.

        Returns:
            UserListResponse with all users
        """
        users = self.user_auth.get_all_users()

        user_responses = [
            UserResponse(
                username=u["username"],
                role=u["role"],
                created_at=u.get("created_at"),
                last_login=u.get("last_login")
            )
            for u in users
        ]

        return UserListResponse(
            users=user_responses,
            total=len(user_responses)
        )

    def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            UserResponse if found, None otherwise
        """
        users = self.user_auth.get_all_users()
        for user in users:
            if user["username"] == username:
                return UserResponse(
                    username=user["username"],
                    role=user["role"],
                    created_at=user.get("created_at"),
                    last_login=user.get("last_login")
                )
        return None

    def create_user(self, user_data: UserCreate, operator: str) -> Tuple[bool, str, Optional[UserResponse]]:
        """
        Create a new user.

        Args:
            user_data: User creation data
            operator: Username of the user performing the operation

        Returns:
            Tuple of (success, message, user_response)
        """
        success, message = self.user_auth.add_user(
            username=user_data.username,
            password=user_data.password,
            role=user_data.role,
            operator=operator
        )

        if success:
            user_response = UserResponse(
                username=user_data.username,
                role=user_data.role,
                created_at=None,  # Will be populated on next query
                last_login=None
            )
            return True, message, user_response

        return False, message, None

    def delete_user(self, username: str, operator: str) -> Tuple[bool, str]:
        """
        Delete a user.

        Args:
            username: Username to delete
            operator: Username of the user performing the operation

        Returns:
            Tuple of (success, message)
        """
        success, message = self.user_auth.delete_user(
            username=username,
            operator=operator
        )

        if success:
            self._cleanup_user_runtime_data(username)

        return success, message

    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Change user password.

        Args:
            username: Username
            old_password: Current password
            new_password: New password

        Returns:
            Tuple of (success, message)
        """
        return self.user_auth.change_password(
            username=username,
            old_password=old_password,
            new_password=new_password
        )

    def reset_password(self, username: str, new_password: str, operator: str) -> Tuple[bool, str]:
        """
        Reset user password (admin operation).

        Args:
            username: Target username
            new_password: New password
            operator: Admin username

        Returns:
            Tuple of (success, message)
        """
        return self.user_auth.reset_password(
            username=username,
            new_password=new_password,
            operator=operator
        )

    def change_role(self, username: str, new_role: str, operator: str) -> Tuple[bool, str]:
        """
        Change user role (admin operation).

        Args:
            username: Target username
            new_role: New role ('admin' or 'user')
            operator: Admin username

        Returns:
            Tuple of (success, message)
        """
        return self.user_auth.change_user_role(
            username=username,
            new_role=new_role,
            operator=operator
        )
