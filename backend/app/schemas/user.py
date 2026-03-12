"""
User management schemas.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    """User schema"""
    username: str = Field(..., min_length=1, max_length=50)
    role: str = Field(..., description="User role: 'admin' or 'user'")
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Create user request schema"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field("user", description="User role: 'admin' or 'user'")


class UserUpdate(BaseModel):
    """Update user request schema"""
    role: Optional[str] = Field(None, description="New user role")
    password: Optional[str] = Field(None, min_length=6, max_length=100, description="New password")


class UserResponse(BaseModel):
    """User response schema"""
    username: str
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    created_by: Optional[str] = None


class UserListResponse(BaseModel):
    """User list response schema"""
    users: List[UserResponse]
    total: int


class ChangePasswordRequest(BaseModel):
    """Change password request schema"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


class ResetPasswordRequest(BaseModel):
    """Reset password request schema (admin only)"""
    username: str
    new_password: str = Field(..., min_length=6, max_length=100)


class ChangeRoleRequest(BaseModel):
    """Change role request schema (admin only)"""
    username: str
    new_role: str = Field(..., description="New role: 'admin' or 'user'")
