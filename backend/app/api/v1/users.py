"""
User management API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.user import (
    UserCreate, UserResponse, UserListResponse,
    ChangePasswordRequest, ResetPasswordRequest, ChangeRoleRequest
)
from app.services.user_service import UserService
from app.dependencies import get_user_service, get_current_user, get_current_admin_user
from tools.user_auth import UserRole

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get all users (admin only).
    """
    return user_service.get_all_users()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Create a new user (admin only).

    - **username**: Username (1-50 characters)
    - **password**: Password (6-100 characters)
    - **role**: User role ('admin' or 'user', default: 'user')
    """
    success, message, user_response = user_service.create_user(
        user_data=user_data,
        operator=current_user["username"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return user_response


@router.get("/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user by username (admin only).
    """
    user = user_service.get_user_by_username(username)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found"
        )

    return user


@router.delete("/{username}")
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Delete a user (admin only).

    Cannot delete yourself or the last admin.
    """
    success, message = user_service.delete_user(
        username=username,
        operator=current_user["username"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return {"message": message, "username": username}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Change own password.

    - **old_password**: Current password
    - **new_password**: New password (6-100 characters)
    """
    success, message = user_service.change_password(
        username=current_user["username"],
        old_password=request.old_password,
        new_password=request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return {"message": message}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Reset user password (admin only).

    - **username**: Target username
    - **new_password**: New password (6-100 characters)
    """
    success, message = user_service.reset_password(
        username=request.username,
        new_password=request.new_password,
        operator=current_user["username"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return {"message": message, "username": request.username}


@router.post("/change-role")
async def change_role(
    request: ChangeRoleRequest,
    current_user: dict = Depends(get_current_admin_user),
    user_service: UserService = Depends(get_user_service)
):
    """
    Change user role (admin only).

    Cannot change your own role or demote the last admin.

    - **username**: Target username
    - **new_role**: New role ('admin' or 'user')
    """
    if request.new_role not in [UserRole.ADMIN, UserRole.USER]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be '{UserRole.ADMIN}' or '{UserRole.USER}'"
        )

    success, message = user_service.change_role(
        username=request.username,
        new_role=request.new_role,
        operator=current_user["username"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return {"message": message, "username": request.username, "new_role": request.new_role}
