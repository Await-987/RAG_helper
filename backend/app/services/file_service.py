"""
File management service.
"""
import os
import sys
from urllib.parse import unquote
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.schemas.file import (
    FileInfo, FileListResponse, FileImportResponse, FileImportStatus,
    FileDeleteResponse, FileDeleteStatus
)


class FileService:
    """File management service"""

    def __init__(self):
        self.storage_dir = settings.STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = settings.COLLECTION_NAME

    def warmup(self) -> None:
        """
        Warm up file-management dependencies used by the backend.

        This ensures storage directories exist and primes the file/database
        status query so the first file-list request is fast.
        """
        from tools.file_manager_ui import MINERU_OUTPUT_DIR, get_local_files_with_db_status

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        MINERU_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        file_info_list, total_chunks = get_local_files_with_db_status(self.storage_dir)
        logger.info(
            f"文件管理预热完成: {len(file_info_list)} 个文件条目, {total_chunks} 个切片"
        )

    def get_file_list(
        self,
        page: int = 1,
        page_size: int = 20,
        file_type: Optional[str] = None
    ) -> FileListResponse:
        """
        Get paginated file list.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            file_type: Filter by type ('imported', 'not_imported', 'ghost', or None for all)

        Returns:
            FileListResponse with paginated file info
        """
        from tools.file_manager_ui import get_local_files_with_db_status

        # Get all files
        file_info_list, total_chunks = get_local_files_with_db_status(self.storage_dir)

        # Filter by type if specified
        if file_type:
            file_info_list = [f for f in file_info_list if f["type"] == file_type]

        # Sort: imported first, then not_imported, then ghost
        type_order = {"imported": 0, "not_imported": 1, "ghost": 2}
        file_info_list.sort(key=lambda x: (type_order.get(x["type"], 3), x["name"]))

        # Paginate
        total_files = len(file_info_list)
        total_pages = max(1, (total_files + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_files = file_info_list[start_idx:end_idx]

        # Convert to FileInfo schema
        files = [
            FileInfo(
                type=f["type"],
                name=f["name"],
                tag=f["tag"],
                path=str(f["path"]) if f.get("path") else None,
                chunk_count=f.get("chunk_count", 0)
            )
            for f in paginated_files
        ]

        return FileListResponse(
            files=files,
            total_files=total_files,
            total_chunks=total_chunks,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            stats={
                "imported": sum(1 for item in file_info_list if item["type"] == "imported"),
                "not_imported": sum(1 for item in file_info_list if item["type"] == "not_imported"),
                "ghost": sum(1 for item in file_info_list if item["type"] == "ghost"),
            }
        )

    def import_files(
        self,
        file_tags: List[str],
        dpi: int = 200,
        debug: bool = False
    ) -> FileImportResponse:
        """
        Import files to database.

        Args:
            file_tags: List of file tags to import
            dpi: MinerU processing DPI
            debug: Enable debug mode

        Returns:
            FileImportResponse with import results
        """
        from tools.file_manager_ui import import_file_to_database, batch_import_files

        # Convert tags to file paths
        file_paths = []
        for tag in file_tags:
            # Tag is relative path like "data/stored_files/file.pdf"
            # Need to convert to absolute path
            if tag.startswith("data/"):
                full_path = PROJECT_ROOT / tag
            else:
                full_path = self.storage_dir / Path(tag).name

            if full_path.exists():
                file_paths.append(str(full_path))
            else:
                logger.warning(f"File not found: {full_path}")

        if not file_paths:
            return FileImportResponse(
                success_count=0,
                failed_count=len(file_tags),
                total=len(file_tags),
                results=[
                    FileImportStatus(
                        file_tag=tag,
                        status="failed",
                        message="File not found"
                    ) for tag in file_tags
                ]
            )

        # Batch import
        result = batch_import_files(
            file_paths=file_paths,
            collection_name=self.collection_name,
            dpi=dpi,
            debug=debug
        )

        # Build response
        import_results = []

        for path in result["success"]:
            tag = self._path_to_tag(path)
            import_results.append(FileImportStatus(
                file_tag=tag,
                status="success",
                message="Import successful"
            ))

        for path, error in result["failed"]:
            tag = self._path_to_tag(path)
            import_results.append(FileImportStatus(
                file_tag=tag,
                status="failed",
                message=error
            ))

        return FileImportResponse(
            success_count=result["success_count"],
            failed_count=result["failed_count"],
            total=result["total"],
            results=import_results
        )

    def delete_files(
        self,
        file_tags: List[str],
        delete_local: bool = True,
        delete_images: bool = True
    ) -> FileDeleteResponse:
        """
        Delete files from database and optionally from local storage.

        Args:
            file_tags: List of file tags to delete
            delete_local: Also delete local files
            delete_images: Also delete associated images

        Returns:
            FileDeleteResponse with delete results
        """
        from tools.file_manager_ui import batch_delete_files_by_tags, delete_local_file

        # Delete from database first
        db_result = batch_delete_files_by_tags(
            file_tags=file_tags,
            collection_name=self.collection_name,
            delete_images=delete_images
        )

        delete_results = []

        # Delete local files if requested
        for tag in file_tags:
            db_deleted = tag not in [t[0] for t in db_result.get("failed_tags", [])]

            local_deleted = False
            if delete_local and db_deleted:
                # Try to delete local file
                file_path = self._tag_to_path(tag)
                if file_path and file_path.exists():
                    local_deleted = delete_local_file(file_path, delete_images=False)

            status = "success" if db_deleted else "failed"
            message = None
            if not db_deleted:
                failed_info = [t for t in db_result.get("failed_tags", []) if t[0] == tag]
                if failed_info:
                    message = failed_info[0][1]

            delete_results.append(FileDeleteStatus(
                file_tag=tag,
                success=db_deleted,
                message=message
            ))

        return FileDeleteResponse(
            success_count=db_result["success_count"],
            failed_count=db_result["failed_count"],
            total=len(file_tags),
            results=delete_results
        )

    def upload_file(self, file_content: bytes, filename: str) -> Tuple[bool, str, Optional[str]]:
        """
        Upload a file to storage directory.

        Args:
            file_content: File content bytes
            filename: Original filename

        Returns:
            Tuple of (success, message, file_tag)
        """
        try:
            # Sanitize filename
            safe_filename = self._sanitize_filename(filename)
            file_path = self.storage_dir / safe_filename

            # Check if file already exists
            if file_path.exists():
                # Add timestamp suffix
                base, ext = os.path.splitext(safe_filename)
                timestamp = int(os.times().elapsed * 1000)
                safe_filename = f"{base}_{timestamp}{ext}"
                file_path = self.storage_dir / safe_filename

            # Write file
            with open(file_path, "wb") as f:
                f.write(file_content)

            # Generate tag
            file_tag = self._path_to_tag(str(file_path))

            logger.info(f"File uploaded: {safe_filename}")
            return True, f"File '{safe_filename}' uploaded successfully", file_tag

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False, f"Upload failed: {str(e)}", None

    def _path_to_tag(self, path: str) -> str:
        """Convert absolute path to relative tag"""
        path_obj = Path(path)
        try:
            return path_obj.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path_obj.as_posix()

    def _tag_to_path(self, tag: str) -> Optional[Path]:
        """Convert tag to absolute path"""
        normalized_tag = unquote(tag.lstrip("/"))
        if normalized_tag.startswith("data/"):
            path = PROJECT_ROOT / normalized_tag
        else:
            path = self.storage_dir / normalized_tag
        if path.exists():
            return path

        # MinerU image references in answers may omit the original PDF prefix.
        # Fall back to suffix matching so `mineru_output/foo_1.jpg` can still
        # resolve to `mineru_output/0【...】foo_1.jpg`.
        if "mineru_output/" in normalized_tag:
            image_name = Path(normalized_tag).name
            mineru_dir = self.storage_dir / "mineru_output"
            if mineru_dir.exists():
                candidate_patterns = [image_name]

                # Some generated answers may slightly alter the bracketed PDF
                # title prefix while preserving the actual image filename suffix.
                if "】" in image_name:
                    suffix_after_bracket = image_name.split("】")[-1]
                    if suffix_after_bracket:
                        candidate_patterns.append(suffix_after_bracket)

                stem = Path(image_name).stem
                extension = Path(image_name).suffix
                if "_" in stem:
                    tail = stem.split("_")[-1]
                    candidate_patterns.append(f"_{tail}{extension}")

                    stem_prefix = stem.rsplit("_", 1)[0]
                    for width in (16, 12, 8):
                        if len(stem_prefix) >= width:
                            candidate_patterns.append(f"{stem_prefix[-width:]}_{tail}{extension}")

                seen_patterns = set()
                for pattern in candidate_patterns:
                    if pattern in seen_patterns:
                        continue
                    seen_patterns.add(pattern)

                    suffix_matches = sorted(mineru_dir.glob(f"*{pattern}"))
                    if suffix_matches:
                        return suffix_matches[0]
        return None

    def get_file_path(self, file_tag: str) -> Optional[Path]:
        """Resolve a file tag or relative storage path to an actual file path."""
        return self._tag_to_path(file_tag)

    def _sanitize_filename(self, filename: str) -> str:
        """支持中文、数字、字母及常用符号的文件名清洗逻辑"""
        import re
        filename = os.path.basename(filename)
        illegal_chars = r'[\\/:*?"<>|]'
        sanitized = re.sub(illegal_chars, "_", filename)
        sanitized = "".join(c for c in sanitized if c.isprintable()).strip(" .")
        sanitized = re.sub(r'_+', '_', sanitized)
        
        return sanitized or "unnamed_file"
