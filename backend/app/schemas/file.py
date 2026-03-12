"""
File management schemas.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """File information schema"""
    type: str = Field(..., description="File type: 'imported', 'not_imported', or 'ghost'")
    name: str = Field(..., description="File name")
    tag: str = Field(..., description="File tag (relative path)")
    path: Optional[str] = Field(None, description="File path (None for ghost files)")
    chunk_count: int = Field(0, description="Number of chunks in database")


class FileListResponse(BaseModel):
    """File list response schema"""
    files: List[FileInfo]
    total_files: int
    total_chunks: int
    page: int
    page_size: int
    total_pages: int
    stats: dict[str, int] = Field(default_factory=dict, description="File counts by type")


class FileUploadResponse(BaseModel):
    """File upload response schema"""
    success: bool
    message: str
    filename: Optional[str] = None
    path: Optional[str] = None


class FileImportRequest(BaseModel):
    """File import request schema"""
    file_tags: List[str] = Field(..., description="List of file tags to import")
    dpi: int = Field(200, description="MinerU processing DPI")
    debug: bool = Field(False, description="Enable debug mode")


class FileImportStatus(BaseModel):
    """File import status schema"""
    file_tag: str
    status: str = Field(..., description="Status: 'pending', 'processing', 'success', 'failed'")
    message: Optional[str] = None
    chunks: Optional[int] = None


class FileImportResponse(BaseModel):
    """File import response schema"""
    success_count: int
    failed_count: int
    total: int
    results: List[FileImportStatus]


class FileDeleteRequest(BaseModel):
    """File delete request schema"""
    file_tags: List[str] = Field(..., description="List of file tags to delete")
    delete_local: bool = Field(True, description="Also delete local files")
    delete_images: bool = Field(True, description="Also delete associated images")


class FileDeleteStatus(BaseModel):
    """File delete status schema"""
    file_tag: str
    success: bool
    message: Optional[str] = None


class FileDeleteResponse(BaseModel):
    """File delete response schema"""
    success_count: int
    failed_count: int
    total: int
    results: List[FileDeleteStatus]
