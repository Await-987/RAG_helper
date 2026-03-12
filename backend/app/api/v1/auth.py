"""
Authentication API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth import LoginRequest, Token, UserResponse
from app.services import AuthService
from app.dependencies import get_auth_service, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Login and get JWT token.

    - **username**: Username
    - **password**: Password
    """
    token, user, error = auth_service.login(request.username, request.password)

    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=3600 * 24  # 24 hours
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current authenticated user info.

    Requires valid JWT token in Authorization header.
    """
    return UserResponse(
        username=current_user["username"],
        role=current_user["role"],
        created_at=current_user.get("created_at"),
        last_login=current_user.get("last_login")
    )


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user)
):
    """
    Logout (client should discard token).

    Note: JWT tokens are stateless, so server-side logout is not required.
    The client should simply discard the token.
    """
    return {"message": "Logged out successfully"}
