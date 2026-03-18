"""
Lightweight import-job tracking for background file indexing.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from loguru import logger

from ..config import settings


IMPORT_JOBS_DIR = settings.STORAGE_ROOT / "import_jobs"
IMPORT_JOBS_DIR.mkdir(parents=True, exist_ok=True)

_job_lock = threading.Lock()
_job_threads: Dict[str, threading.Thread] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _job_path(job_id: str) -> Path:
    return IMPORT_JOBS_DIR / f"{job_id}.json"


def _write_job(job: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(job["job_id"])
    path = _job_path(job_id)
    temp_path = path.with_suffix(".tmp")
    payload = json.dumps(job, ensure_ascii=False, indent=2)
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)
    return dict(job)


def _reconcile_job_state(job: Dict[str, Any]) -> Dict[str, Any]:
    status = str(job.get("status") or "")
    job_id = str(job.get("job_id") or "")
    thread = _job_threads.get(job_id)

    if status in {"queued", "running"} and (thread is None or not thread.is_alive()):
        job = dict(job)
        job["status"] = "failed"
        job["error"] = job.get("error") or "后台导入线程已停止或服务已重启"
        job["message"] = job.get("message") or "后台导入线程已停止或服务已重启"
        job["finished_at"] = job.get("finished_at") or _now_iso()
        job["updated_at"] = _now_iso()
        _write_job(job)
        _job_threads.pop(job_id, None)
        logger.warning(f"Import job marked failed because worker thread stopped: {job_id}")

    return job


def create_import_job(*, file_tags: list[str], dpi: int, debug: bool) -> Dict[str, Any]:
    now = _now_iso()
    job = {
        "job_id": uuid.uuid4().hex,
        "status": "queued",
        "message": "后台导入任务已提交",
        "error": None,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "current_index": 0,
        "current_file_tag": None,
        "total": len(file_tags),
        "success_count": 0,
        "failed_count": 0,
        "request": {
            "file_tags": list(file_tags),
            "dpi": int(dpi),
            "debug": bool(debug),
        },
        "results": [
            {
                "file_tag": tag,
                "status": "pending",
                "message": None,
                "chunks": None,
            }
            for tag in file_tags
        ],
    }
    with _job_lock:
        return _write_job(job)


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_path(job_id)
    if not path.exists():
        return None
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Failed to load import job {job_id}: {exc}")
        return None
    return _reconcile_job_state(job)


def save_import_job(job: Dict[str, Any]) -> Dict[str, Any]:
    job = dict(job)
    job["updated_at"] = _now_iso()
    with _job_lock:
        return _write_job(job)


def update_import_job(job_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
    job = get_import_job(job_id)
    if job is None:
        return None
    job.update(updates)
    return save_import_job(job)


def get_active_import_job() -> Optional[Dict[str, Any]]:
    jobs = []
    for path in IMPORT_JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        jobs.append(_reconcile_job_state(job))

    active_jobs = [job for job in jobs if str(job.get("status")) in {"queued", "running"}]
    if not active_jobs:
        return None
    active_jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return active_jobs[0]


def start_import_job(job_id: str, runner: Callable[[str], None]) -> None:
    def _target() -> None:
        try:
            runner(job_id)
        except Exception as exc:
            logger.exception(f"Import job crashed: {job_id}")
            update_import_job(
                job_id,
                status="failed",
                message=f"导入任务异常终止: {exc}",
                error=str(exc),
                finished_at=_now_iso(),
            )
        finally:
            with _job_lock:
                _job_threads.pop(job_id, None)

    thread = threading.Thread(
        target=_target,
        name=f"import-job-{job_id}",
        daemon=True,
    )
    with _job_lock:
        _job_threads[job_id] = thread
    thread.start()
