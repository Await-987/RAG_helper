"""
Shared storage path helpers.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


SHARED_STORAGE_ROOT_VALUE = os.getenv("SHARED_STORAGE_ROOT", "data")
SHARED_STORAGE_ROOT = _resolve_project_path(SHARED_STORAGE_ROOT_VALUE)

try:
    SHARED_STORAGE_ROOT_REL = SHARED_STORAGE_ROOT.relative_to(PROJECT_ROOT).as_posix()
except ValueError:
    SHARED_STORAGE_ROOT_REL = SHARED_STORAGE_ROOT_VALUE

LEGACY_SHARED_STORAGE_ROOT_REL = "data"

STORED_FILES_DIR = SHARED_STORAGE_ROOT / "stored_files"
MINERU_OUTPUT_DIR = STORED_FILES_DIR / "mineru_output"
CONTENT_LISTS_DIR = SHARED_STORAGE_ROOT / "content_lists"
EXPORTED_CHUNKS_DIR = SHARED_STORAGE_ROOT / "exported_chunks"
AGENT_MEMORY_DIR = SHARED_STORAGE_ROOT / "agent_memory"
CHAT_SESSION_DIR = SHARED_STORAGE_ROOT / "chat_sessions"


def project_relative_path(path: Path | str) -> str:
    path_obj = Path(path)
    try:
        return path_obj.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path_obj.as_posix()


def shared_storage_prefix_matches(tag: str) -> bool:
    normalized = tag.lstrip("/")
    if normalized.startswith(f"{SHARED_STORAGE_ROOT_REL}/"):
        return True
    return normalized.startswith(f"{LEGACY_SHARED_STORAGE_ROOT_REL}/")


def tag_to_project_path(tag: str) -> Optional[Path]:
    normalized = tag.lstrip("/")
    candidates = [normalized]

    if normalized.startswith(f"{SHARED_STORAGE_ROOT_REL}/"):
        candidates.append(
            f"{LEGACY_SHARED_STORAGE_ROOT_REL}/{normalized.removeprefix(f'{SHARED_STORAGE_ROOT_REL}/')}"
        )
    elif normalized.startswith(f"{LEGACY_SHARED_STORAGE_ROOT_REL}/"):
        candidates.append(
            f"{SHARED_STORAGE_ROOT_REL}/{normalized.removeprefix(f'{LEGACY_SHARED_STORAGE_ROOT_REL}/')}"
        )

    for candidate in candidates:
        path = PROJECT_ROOT / candidate
        if path.exists():
            return path

    # Fall back to the primary candidate even if it does not exist yet.
    return PROJECT_ROOT / candidates[0] if candidates else None
