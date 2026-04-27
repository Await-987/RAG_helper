"""
File management API routes.
"""
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Request
from fastapi.responses import FileResponse

from app.schemas.file import (
    FileListResponse, FileImportRequest, FileImportResponse,
    FileDeleteRequest, FileDeleteResponse, FileUploadResponse
)
from app.services.file_service import FileService
from app.dependencies import get_file_service, get_current_user, get_current_admin_user
from app.core.security import verify_token
from app.services.auth_service import AuthService

router = APIRouter(prefix="/files", tags=["Files"])


async def get_user_from_header_or_token(
    request: Request,
    token: Optional[str] = Query(None)
) -> dict:
    """
    Get current user from Authorization header or token query parameter.
    Used for endpoints that need direct link access (e.g., file preview).
    """
    # Try header first
    auth_header = request.headers.get("Authorization", "")
    jwt_token = None

    if auth_header.startswith("Bearer "):
        jwt_token = auth_header[7:]
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    payload = verify_token(jwt_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    auth_service = AuthService()
    user = auth_service.get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    file_type: Optional[str] = Query(None, description="Filter by type: 'imported', 'not_imported', 'ghost'"),
    search: Optional[str] = Query(None, description="Keyword search across the full file list before pagination"),
    force_refresh: bool = Query(False, description="Bypass file-status caches and recompute the latest state"),
    current_user: dict = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Get paginated file list.

    - **page**: Page number (1-indexed)
    - **page_size**: Number of items per page
    - **file_type**: Filter by type ('imported', 'not_imported', 'ghost')
    - **search**: Keyword search applied before pagination
    """
    return file_service.get_file_list(
        page=page,
        page_size=page_size,
        file_type=file_type,
        search=search,
        force_refresh=force_refresh,
    )


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Upload a file to storage (admin only).

    The file will be stored in the storage directory but not automatically imported.
    Use the /import endpoint to import files to the database.

    - **file**: File to upload
    """
    # Check file type (only allow PDF and common document formats)
    allowed_extensions = {".pdf", ".doc", ".docx", ".txt", ".md"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file_ext}' not allowed. Allowed types: {allowed_extensions}"
        )

    # Read file content
    content = await file.read()

    # Upload file
    success, message, file_tag = file_service.upload_file(content, file.filename)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message
        )

    return FileUploadResponse(
        success=True,
        message=message,
        filename=file.filename,
        path=file_tag
    )


def _serve_file_content(file_tag: str, file_service: FileService) -> FileResponse:
    file_path = file_service.get_file_path(file_tag)

    if file_path is None or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_tag}' not found"
        )

    return FileResponse(path=file_path)


@router.get("/content")
async def get_file_content_by_query(
    request: Request,
    file_tag: str = Query(..., description="Stable file tag such as `data/stored_files/a.pdf`"),
    token: Optional[str] = Query(None, description="JWT token (alternative to header)"),
    current_user: dict = Depends(get_user_from_header_or_token),
    file_service: FileService = Depends(get_file_service)
):
    """
    Serve a stored file or generated image via query parameter.

    This is the preferred endpoint because `file_tag` is treated as an opaque
    identifier instead of being split by the router path parser.
    """
    return _serve_file_content(file_tag=file_tag, file_service=file_service)


@router.get("/content/{file_tag:path}")
async def get_file_content(
    file_tag: str,
    request: Request,
    token: Optional[str] = Query(None, description="JWT token (alternative to header)"),
    current_user: dict = Depends(get_user_from_header_or_token),
    file_service: FileService = Depends(get_file_service)
):
    """
    Serve a stored file or generated image for preview/download.

    Authentication: Authorization header or ?token=xxx query parameter

    - **file_tag**: Relative storage path such as `data/stored_files/a.pdf`
      or `shared-files/stored_files/a.pdf`
      or `mineru_output/example.jpg`
      or just filename: `GB50229-2019.pdf`
    - **token**: Optional JWT token via query parameter (for direct link access)
    """
    return _serve_file_content(file_tag=file_tag, file_service=file_service)


@router.post("/import", response_model=FileImportResponse)
async def import_files(
    request: FileImportRequest,
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Import files to the vector database (admin only).

    This processes files with MinerU and stores the chunks in Qdrant.

    - **file_tags**: List of file tags to import
    - **dpi**: MinerU processing DPI (default: 200)
    - **debug**: Enable debug mode
    """
    if not request.file_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file tags provided"
        )
    try:
        return file_service.import_files(
            file_tags=request.file_tags,
            dpi=request.dpi,
            debug=request.debug
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/import-jobs/active", response_model=FileImportResponse)
async def get_active_import_job(
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    job = file_service.get_active_import_job_status()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active import job"
        )
    return job


@router.get("/import-jobs/{job_id}", response_model=FileImportResponse)
async def get_import_job(
    job_id: str,
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    job = file_service.get_import_job_status(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import job '{job_id}' not found"
        )
    return job


@router.delete("", response_model=FileDeleteResponse)
async def delete_files(
    request: FileDeleteRequest,
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Delete files from database and optionally from storage (admin only).

    - **file_tags**: List of file tags to delete
    - **delete_local**: Also delete local files (default: true)
    - **delete_images**: Also delete associated images (default: true)
    """
    if not request.file_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file tags provided"
        )

    return file_service.delete_files(
        file_tags=request.file_tags,
        delete_local=request.delete_local,
        delete_images=request.delete_images
    )


@router.delete("/{file_tag:path}", response_model=FileDeleteResponse)
async def delete_single_file(
    file_tag: str,
    delete_local: bool = Query(True, description="Also delete local file"),
    delete_images: bool = Query(True, description="Also delete associated images"),
    current_user: dict = Depends(get_current_admin_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Delete a single file from database and optionally from storage (admin only).

    - **file_tag**: File tag to delete (URL-encoded path)
    - **delete_local**: Also delete local file
    - **delete_images**: Also delete associated images
    """
    return file_service.delete_files(
        file_tags=[file_tag],
        delete_local=delete_local,
        delete_images=delete_images
    )
