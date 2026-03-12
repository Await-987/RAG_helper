"""
Authentication schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Login request schema"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class Token(BaseModel):
    """Token response schema"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiration time in seconds")


class TokenData(BaseModel):
    """Token payload data"""
    sub: Optional[str] = None  # username
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None


class UserResponse(BaseModel):
    """User response schema (without sensitive data)"""
    username: str
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None

    class Config:
        from_attributes = True
