"""
File management API routes.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse

from app.schemas.file import (
    FileListResponse, FileImportRequest, FileImportResponse,
    FileDeleteRequest, FileDeleteResponse, FileUploadResponse
)
from app.services.file_service import FileService
from app.dependencies import get_file_service, get_current_user, get_current_admin_user

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    file_type: Optional[str] = Query(None, description="Filter by type: 'imported', 'not_imported', 'ghost'"),
    search: Optional[str] = Query(None, description="Keyword search across the full file list before pagination"),
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


@router.get("/content/{file_tag:path}")
async def get_file_content(
    file_tag: str,
    current_user: dict = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Serve a stored file or generated image for preview/download.

    - **file_tag**: Relative storage path such as `data/stored_files/a.pdf`
      or `shared-files/stored_files/a.pdf`
      or `mineru_output/example.jpg`
    """
    file_path = file_service.get_file_path(file_tag)

    if file_path is None or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_tag}' not found"
        )

    return FileResponse(path=file_path)


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
