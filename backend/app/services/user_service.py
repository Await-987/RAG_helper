"""
User management service.
"""
import sys
from pathlib import Path
from typing import List, Tuple, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.user_auth import UserAuth, UserRole
from app.schemas.user import User, UserCreate, UserResponse, UserListResponse


class UserService:
    """User management service"""

    def __init__(self):
        self.user_auth = UserAuth()

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
        return self.user_auth.delete_user(
            username=username,
            operator=operator
        )

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
