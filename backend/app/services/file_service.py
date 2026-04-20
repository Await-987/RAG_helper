"""
File management service.
"""
import os
import re
import unicodedata
from datetime import datetime
from urllib.parse import unquote
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from loguru import logger

from app.config import settings
from app.core.import_jobs import (
    create_import_job,
    get_active_import_job,
    get_import_job,
    save_import_job,
    start_import_job,
)
from app.schemas.file import (
    FileInfo, FileListResponse, FileImportResponse, FileImportStatus,
    FileDeleteResponse, FileDeleteStatus
)
from storage_paths import (
    PROJECT_ROOT,
    project_relative_path,
    tag_to_project_path,
    SHARED_STORAGE_ROOT_REL,
    LEGACY_SHARED_STORAGE_ROOT_REL,
)


class FileService:
    """File management service"""

    def __init__(self):
        self.storage_dir = settings.STORAGE_DIR
        self.mineru_output_dir = settings.MINERU_OUTPUT_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.mineru_output_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = settings.COLLECTION_NAME

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    def warmup(self) -> None:
        """
        Warm up file-management dependencies used by the backend.

        This ensures storage directories exist and primes the file/database
        status query so the first file-list request is fast.
        """
        from app.core.file_catalog import MINERU_OUTPUT_DIR, get_local_files_with_db_status

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
        file_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> FileListResponse:
        """
        Get paginated file list.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            file_type: Filter by type ('imported', 'not_imported', 'ghost', or None for all)
            search: Keyword search across all files before pagination

        Returns:
            FileListResponse with paginated file info
        """
        from app.core.file_catalog import get_local_files_with_db_status

        # Get all files
        file_info_list, total_chunks = get_local_files_with_db_status(self.storage_dir)
        all_file_info_list = list(file_info_list)

        global_stats = {
            "imported": sum(1 for item in all_file_info_list if item["type"] == "imported"),
            "not_imported": sum(1 for item in all_file_info_list if item["type"] == "not_imported"),
            "ghost": sum(1 for item in all_file_info_list if item["type"] == "ghost"),
        }

        # Filter by type if specified
        if file_type:
            file_info_list = [f for f in file_info_list if f["type"] == file_type]

        type_order = {"imported": 0, "not_imported": 1, "ghost": 2}

        normalized_search = self._normalize_search_query(search)
        if normalized_search:
            file_info_list = [
                item for item in file_info_list
                if self._file_matches_search(item, normalized_search)
            ]
            file_info_list.sort(
                key=lambda item: self._search_sort_key(
                    item,
                    normalized_search,
                    type_order=type_order,
                )
            )
        else:
            # Default ordering: imported first, then not_imported, then ghost
            file_info_list.sort(key=lambda x: (type_order.get(x["type"], 3), x["name"].lower()))

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
            stats=global_stats,
        )

    @staticmethod
    def _normalize_search_query(search: Optional[str]) -> str:
        return re.sub(r"\s+", " ", (search or "").strip().lower())

    @classmethod
    def _search_keywords(cls, search: str) -> List[str]:
        return [token for token in re.split(r"\s+", search) if token]

    @classmethod
    def _file_matches_search(cls, item: Dict, search: str) -> bool:
        keywords = cls._search_keywords(search)
        if not keywords:
            return True

        name = str(item.get("name") or "").lower()
        tag = str(item.get("tag") or "").lower()
        haystack = f"{name} {tag}"

        if search in haystack:
            return True
        return all(keyword in haystack for keyword in keywords)

    @classmethod
    def _search_sort_key(cls, item: Dict, search: str, *, type_order: Dict[str, int]) -> tuple:
        name = str(item.get("name") or "")
        name_lower = name.lower()
        tag_lower = str(item.get("tag") or "").lower()
        keywords = cls._search_keywords(search)

        exact_match = 0 if name_lower == search else 1
        prefix_match = 0 if name_lower.startswith(search) else 1
        contains_full = 0 if search in name_lower else 1

        if search in name_lower:
            first_position = name_lower.find(search)
        else:
            positions = [name_lower.find(keyword) for keyword in keywords if keyword in name_lower]
            first_position = min(positions) if positions else len(name_lower) + len(tag_lower) + 1

        keyword_hits = sum(1 for keyword in keywords if keyword in name_lower or keyword in tag_lower)
        return (
            exact_match,
            prefix_match,
            contains_full,
            -keyword_hits,
            first_position,
            type_order.get(str(item.get("type")), 3),
            len(name_lower),
            name_lower,
            tag_lower,
        )

    def import_files(
        self,
        file_tags: List[str],
        dpi: int = 200,
        debug: bool = False
    ) -> FileImportResponse:
        """
        Submit file import as a background job.

        Args:
            file_tags: List of file tags to import
            dpi: MinerU processing DPI
            debug: Enable debug mode

        Returns:
            FileImportResponse with import job status
        """
        active_job = get_active_import_job()
        if active_job is not None:
            raise RuntimeError(
                f"已有导入任务正在执行: {active_job['job_id']}"
            )

        job = create_import_job(
            file_tags=file_tags,
            dpi=dpi,
            debug=debug,
        )
        start_import_job(job["job_id"], self._run_import_job)
        latest_job = get_import_job(job["job_id"])
        if latest_job is None:
            raise RuntimeError("导入任务创建成功，但读取任务状态失败")
        return FileImportResponse(**latest_job)

    def get_import_job_status(self, job_id: str) -> Optional[FileImportResponse]:
        job = get_import_job(job_id)
        if job is None:
            return None
        return FileImportResponse(**job)

    def get_active_import_job_status(self) -> Optional[FileImportResponse]:
        job = get_active_import_job()
        if job is None:
            return None
        return FileImportResponse(**job)

    def _run_import_job(self, job_id: str) -> None:
        from app.core.file_catalog import clear_local_file_status_cache, import_file_to_database
        logger.info(f"[Import] 开始导入任务 {job_id}，共 {len(list((dict((get_import_job(job_id) or {}).get('request') or {})).get('file_tags') or []))} 个文件")

        job = get_import_job(job_id)
        if job is None:
            logger.error(f"Import job not found: {job_id}")
            return

        request = dict(job.get("request") or {})
        file_tags = list(request.get("file_tags") or [])
        dpi = int(request.get("dpi") or 200)
        debug = bool(request.get("debug") or False)

        job["status"] = "running"
        job["message"] = "后台导入任务执行中"
        job["started_at"] = job.get("started_at") or self._now_iso()
        save_import_job(job)

        # Convert tags to file paths
        file_entries: List[Tuple[str, Path]] = []
        results_by_tag = {
            str(item.get("file_tag")): dict(item)
            for item in job.get("results", [])
            if item.get("file_tag")
        }

        for tag in file_tags:
            # Tag is relative path like "data/stored_files/file.pdf"
            # Need to convert to absolute path
            if tag.startswith(f"{SHARED_STORAGE_ROOT_REL}/") or tag.startswith(f"{LEGACY_SHARED_STORAGE_ROOT_REL}/"):
                full_path = tag_to_project_path(tag)
            else:
                full_path = self.storage_dir / Path(tag).name

            if full_path is not None and full_path.exists():
                file_entries.append((tag, full_path))
            else:
                logger.warning(f"File not found: {full_path}")
                item = results_by_tag.get(tag, {"file_tag": tag, "status": "pending", "message": None, "chunks": None})
                item["status"] = "failed"
                item["message"] = "File not found"
                results_by_tag[tag] = item
                job["failed_count"] = int(job.get("failed_count") or 0) + 1

        job["results"] = list(results_by_tag.values())
        save_import_job(job)

        if not file_entries:
            job["status"] = "failed"
            job["message"] = "没有可导入的文件"
            job["error"] = "No valid files to import"
            job["finished_at"] = self._now_iso()
            save_import_job(job)
            clear_local_file_status_cache()
            return

        for index, (tag, full_path) in enumerate(file_entries, start=1):
            job = get_import_job(job_id) or job
            job["current_index"] = index
            job["current_file_tag"] = tag
            job["message"] = f"正在导入 {Path(full_path).name} ({index}/{len(file_entries)})"
            item = results_by_tag.get(tag, {"file_tag": tag, "status": "pending", "message": None, "chunks": None})
            item["status"] = "processing"
            item["message"] = "处理中"
            results_by_tag[tag] = item
            job["results"] = list(results_by_tag.values())
            save_import_job(job)

            success, message, chunks = import_file_to_database(
                file_path=str(full_path),
                collection_name=self.collection_name,
                dpi=dpi,
                debug=debug,
            )
            logger.info(f"[Import] {Path(full_path).name} → {'成功' if success else '失败'}: {message}")
            item["status"] = "success" if success else "failed"
            item["message"] = message
            item["chunks"] = chunks
            results_by_tag[tag] = item

            if success:
                job["success_count"] = int(job.get("success_count") or 0) + 1
            else:
                job["failed_count"] = int(job.get("failed_count") or 0) + 1

            job["results"] = list(results_by_tag.values())
            save_import_job(job)

        job = get_import_job(job_id) or job
        job["status"] = "completed"
        job["message"] = (
            f"导入完成：成功 {job.get('success_count', 0)} 个，失败 {job.get('failed_count', 0)} 个"
        )
        job["current_file_tag"] = None
        job["finished_at"] = self._now_iso()
        save_import_job(job)
        clear_local_file_status_cache()
        logger.info(f"[Import] 任务 {job_id} 完成：成功 {job.get('success_count', 0)}，失败 {job.get('failed_count', 0)}")

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
        from app.core.file_catalog import batch_delete_files_by_tags, delete_local_file

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
            from app.core.file_catalog import clear_local_file_status_cache

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

            # File list results are cached for 60s; invalidate immediately so
            # the newly uploaded file shows up on the next list request.
            clear_local_file_status_cache()

            logger.info(f"File uploaded: {safe_filename}")
            return True, f"File '{safe_filename}' uploaded successfully", file_tag

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False, f"Upload failed: {str(e)}", None

    def _path_to_tag(self, path: str) -> str:
        """Convert absolute path to relative tag"""
        return project_relative_path(Path(path))

    def _tag_to_path(self, tag: str) -> Optional[Path]:
        """Convert tag to absolute path"""
        normalized_tag = unquote(tag.lstrip("/"))
        shared_stored_prefix = f"{SHARED_STORAGE_ROOT_REL}/stored_files/"
        if normalized_tag.startswith(f"{shared_stored_prefix}mineru_output/"):
            path = self.storage_dir / normalized_tag.removeprefix(shared_stored_prefix)
        elif normalized_tag.startswith("data/stored_files/mineru_output/"):
            path = self.storage_dir / normalized_tag.removeprefix("data/stored_files/")
        elif normalized_tag.startswith("data/mineru_output/"):
            path = PROJECT_ROOT / normalized_tag
        elif normalized_tag.startswith("mineru_output/"):
            path = self.storage_dir / normalized_tag
        else:
            if "/" in normalized_tag:
                path = tag_to_project_path(normalized_tag)
            else:
                path = self.storage_dir / normalized_tag
        if path is not None and path.exists():
            return path

        # Chat answers may cite a source as "GB/T 6451-2015 第 6.1.3条" or
        # "GB/T 6451-2015 表1". Fall back to filename matching by standard id.
        fallback_path = self._resolve_source_reference(normalized_tag)
        if fallback_path is not None:
            return fallback_path

        # MinerU image references in answers may omit the original PDF prefix.
        # Fall back to suffix matching so `mineru_output/foo_1.jpg` can still
        # resolve to `mineru_output/0【...】foo_1.jpg`.
        if "mineru_output/" in normalized_tag:
            image_name = Path(normalized_tag).name
            mineru_dirs = [self.storage_dir / "mineru_output"]
            if self.mineru_output_dir not in mineru_dirs:
                mineru_dirs.append(self.mineru_output_dir)

            for mineru_dir in mineru_dirs:
                if not mineru_dir.exists():
                    continue
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

    @staticmethod
    def _strip_source_locator(source: str) -> str:
        """Remove trailing section/table locators from LLM-generated source text."""
        value = unquote((source or "").strip())
        value = value.strip(" \t\r\n\"'`“”‘’")
        value = re.sub(r"\s+", " ", value)

        locator_patterns = (
            r"[\s（(【\[]第\s*\d+(?:\.\d+){0,6}\s*(?:条|款|项|节|章)?(?:[）)】\]]+)?",
            r"[\s（(【\[]表\s*[A-Za-z]?\d+(?:[-—]\d+)?(?:[）)】\]]+)?",
            r"[\s（(【\[]图\s*[A-Za-z]?\d+(?:[-—]\d+)?(?:[）)】\]]+)?",
            r"[\s（(【\[]附录\s*[A-Za-z0-9一二三四五六七八九十]+(?:[）)】\]]+)?",
        )
        for pattern in locator_patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                value = value[:match.start()].strip(" \t\r\n,，;；:：-—（）()【】[]")

        return value

    @staticmethod
    def _normalize_source_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value or "").lower()
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)

    def _resolve_source_reference(self, raw_reference: str) -> Optional[Path]:
        """Map a source label to the closest stored file name."""
        reference = unquote((raw_reference or "").strip())
        if not reference or not self.storage_dir.exists():
            return None

        candidate_texts: List[str] = []
        for candidate in (
            reference,
            Path(reference).name,
            self._strip_source_locator(reference),
            self._strip_source_locator(Path(reference).name),
        ):
            cleaned = (candidate or "").strip().strip(" \t\r\n\"'`")
            if cleaned and cleaned not in candidate_texts:
                candidate_texts.append(cleaned)

        for candidate in candidate_texts:
            direct_path = self.storage_dir / candidate
            if direct_path.exists():
                return direct_path

            if not Path(candidate).suffix:
                for extension in (".pdf", ".doc", ".docx", ".txt", ".md"):
                    direct_with_ext = self.storage_dir / f"{candidate}{extension}"
                    if direct_with_ext.exists():
                        return direct_with_ext

        stored_files = [path for path in self.storage_dir.iterdir() if path.is_file()]
        if not stored_files:
            return None

        best_match: Optional[Path] = None
        best_rank: Optional[Tuple[int, int, int, str]] = None

        for candidate in candidate_texts:
            candidate_key = self._normalize_source_key(candidate)
            if not candidate_key:
                continue

            for path in stored_files:
                file_name = path.name
                stem = path.stem
                file_key = self._normalize_source_key(file_name)
                stem_key = self._normalize_source_key(stem)
                rank: Optional[Tuple[int, int, int, str]] = None

                if candidate.lower() == file_name.lower() or candidate.lower() == stem.lower():
                    rank = (0, 0 if path.suffix.lower() == ".pdf" else 1, len(file_name), file_name)
                elif candidate_key == file_key or candidate_key == stem_key:
                    rank = (1, 0 if path.suffix.lower() == ".pdf" else 1, len(file_name), file_name)
                elif file_key.startswith(candidate_key) or stem_key.startswith(candidate_key):
                    rank = (2, 0 if path.suffix.lower() == ".pdf" else 1, len(file_name), file_name)
                elif candidate_key in file_key or candidate_key in stem_key:
                    rank = (3, 0 if path.suffix.lower() == ".pdf" else 1, len(file_name), file_name)

                if rank is not None and (best_rank is None or rank < best_rank):
                    best_match = path
                    best_rank = rank

        return best_match

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
