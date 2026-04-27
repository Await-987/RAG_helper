"""
Chat service with session management.
"""
import uuid
import json
import re
from pathlib import Path
from contextlib import suppress
from datetime import datetime
from typing import Dict, Optional, Generator, Any, Tuple, List
from urllib.parse import urlencode
from loguru import logger
from pydantic import BaseModel, Field

from camel.agents.chat_agent import ChatAgent
from camel.messages.base import BaseMessage
from camel.types import OpenAIBackendRole

from app.config import settings
from app.core.redis_client import get_redis_client
from app.schemas.chat import ChatMessage, ChatContentBlock


class IntentRoutingDecision(BaseModel):
    """Structured output for deciding whether a turn needs forced KB search."""

    needs_search: bool = Field(..., description="Whether this turn should force a knowledge-base retrieval before answering.")
    confidence: float = Field(..., description="Confidence score between 0 and 1.")
    reason: str = Field(..., description="Short reason for the routing decision.")


class SearchRewritePlan(BaseModel):
    """Structured output for context-aware KB query rewriting."""

    query: str = Field(..., description="A compact retrieval query with the referent filled in.")
    intent_description: str = Field(..., description="A complete natural-language search intent with resolved references.")
    expanded_queries: List[str] = Field(
        default_factory=list,
        description="Up to two additional retrieval queries for aliases, synonyms, table names, or missing facets.",
    )
    referent: str = Field(default="", description="The resolved referent or subject from recent context.")
    reason: str = Field(default="", description="Short explanation for the rewrite plan.")


class RedisSessionStore:
    """Redis-backed session metadata and user session index."""

    def __init__(self):
        self._client = get_redis_client()
        self._prefix = settings.REDIS_PREFIX.strip() or "rag"
        self._warned_unavailable = False

    def is_enabled(self) -> bool:
        return self._client is not None

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}:chat:session:{session_id}"

    def _user_sessions_key(self, username: str) -> str:
        return f"{self._prefix}:chat:user:{username}:sessions"

    @staticmethod
    def _updated_score(metadata: dict) -> float:
        updated_at = str(metadata.get("updated_at") or metadata.get("last_activity") or "")
        try:
            return datetime.fromisoformat(updated_at).timestamp()
        except Exception:
            return datetime.now().timestamp()

    def _log_unavailable(self, exc: Exception) -> None:
        if self._warned_unavailable:
            return
        logger.warning(f"Redis session store unavailable, falling back to local state/files: {exc}")
        self._warned_unavailable = True

    def upsert_session(self, metadata: dict) -> bool:
        if self._client is None:
            return False
        username = str(metadata.get("username") or "").strip()
        session_id = str(metadata.get("session_id") or "").strip()
        if not username or not session_id:
            return False

        payload = json.dumps(metadata, ensure_ascii=False)
        try:
            pipeline = self._client.pipeline()
            pipeline.set(self._session_key(session_id), payload)
            pipeline.zadd(self._user_sessions_key(username), {session_id: self._updated_score(metadata)})
            pipeline.execute()
            return True
        except Exception as exc:
            self._log_unavailable(exc)
            return False

    def get_session(self, session_id: str) -> Optional[dict]:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._session_key(session_id))
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception as exc:
            self._log_unavailable(exc)
            return None

    def list_sessions_for_user(self, username: str) -> List[dict]:
        if self._client is None:
            return []
        try:
            session_ids = self._client.zrevrange(self._user_sessions_key(username), 0, -1)
        except Exception as exc:
            self._log_unavailable(exc)
            return []

        sessions: List[dict] = []
        missing_ids: List[str] = []
        for session_id in session_ids:
            metadata = self.get_session(session_id)
            if not metadata:
                missing_ids.append(session_id)
                continue
            if metadata.get("username") == username:
                sessions.append(metadata)

        if missing_ids:
            try:
                self._client.zrem(self._user_sessions_key(username), *missing_ids)
            except Exception:
                pass
        return sessions

    def delete_session(self, username: str, session_id: str) -> None:
        if self._client is None:
            return
        try:
            pipeline = self._client.pipeline()
            pipeline.delete(self._session_key(session_id))
            pipeline.zrem(self._user_sessions_key(username), session_id)
            pipeline.execute()
        except Exception as exc:
            self._log_unavailable(exc)


def _normalize_line_endings(content: str) -> str:
    return (content or "").replace("\r\n", "\n")


def _normalize_latex_delimiters(content: str) -> str:
    return (
        content
        .replace("\\[", "$$\n")
        .replace("\\]", "\n$$")
        .replace("\\(", "$")
        .replace("\\)", "$")
    )


def _strip_formula_bullet(line: str) -> str:
    return re.sub(r"^[•·●▪◦‣\-*]+\s*", "", line).strip()


def _looks_like_formula_line(line: str) -> bool:
    trimmed = _strip_formula_bullet(line.strip())
    if not trimmed or "$$" in trimmed or "$" in trimmed:
        return False
    if re.match(r"^(其中|说明|注[:：]?|例如|比如|如下|定义|可得|因此|所以|来源[:：]?|应用场景[:：]?|参数说明[:：]?)", trimmed):
        return False
    if len(trimmed) > 180:
        return False
    latex_signal = re.search(
        r"\\(?:frac|sqrt|left|right|mathrm|mathbf|mathcal|mathfrak|text|alpha|beta|gamma|delta|theta|phi|rho|mu|sigma|lambda|omega|sin|cos|tan|log|ln|quad|cdot|times)\b",
        trimmed,
    )
    subscript_signal = re.search(r"[_^](?:\{[^}]+\}|[A-Za-z0-9])", trimmed)
    operator_signal = re.search(r"[=+\-*/^]", trimmed)
    if re.search(r"[，。；！？]", trimmed) and not re.search(r"\\text\{.*\}", trimmed):
        return False
    return bool((latex_signal or subscript_signal) and (operator_signal or latex_signal))


def _merge_formula_lines(lines: List[str]) -> Optional[str]:
    normalized = [_strip_formula_bullet(line.strip()) for line in lines if line.strip()]
    if not normalized:
        return None
    merged = " ".join(normalized)
    merged = re.sub(r"\s*([=+\-*/^])\s*", r" \1 ", merged)
    merged = re.sub(r"\s+([)\]}])", r"\1", merged)
    merged = re.sub(r"([({\[])\s+", r"\1", merged)
    merged = re.sub(r"\s{2,}", " ", merged).strip()
    if not re.search(r"\\(?:frac|sqrt|left|right|mathrm|mathbf|mathcal|text|alpha|beta|gamma|delta|theta|phi|rho|mu|sigma|lambda|omega|sin|cos|tan|log|ln|quad|cdot|times)\b", merged):
        return None
    if re.search(r"\\(?:mathrm|mathbf|mathcal|mathfrak|text)\{[^}]+\}\{[^}]+\}", merged):
        return None
    return merged


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^\|.*\|$", stripped) or re.match(r"^[^|\n]+(\|[^|\n]+){2,}$", stripped))


def _is_table_separator(line: str) -> bool:
    normalized = line.strip().lstrip("|").rstrip("|")
    cells = [cell.strip() for cell in normalized.split("|") if cell.strip()]
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell) for cell in cells)


def _extract_table_from_fenced_code_block(content: str) -> Optional[str]:
    stripped = content.strip()
    match = re.fullmatch(r"```([A-Za-z0-9_-]+)?\s*\n([\s\S]*?)\n```", stripped)
    if not match:
        return None

    language = (match.group(1) or "").strip().lower()
    if language and language not in {"markdown", "md"}:
        return None

    inner = (match.group(2) or "").strip()
    if not inner:
        return None

    non_empty_lines = [line.strip() for line in inner.split("\n") if line.strip()]
    if not non_empty_lines:
        return None

    if re.match(r"^<table[\s>]", non_empty_lines[0], re.IGNORECASE):
        return inner

    if len(non_empty_lines) >= 2 and _is_table_row(non_empty_lines[0]) and _is_table_separator(non_empty_lines[1]):
        return inner

    return None


def _build_content_blocks(content: str) -> List[ChatContentBlock]:
    normalized = _normalize_latex_delimiters(_normalize_line_endings(content)).strip()
    if not normalized:
        return []

    lines = normalized.split("\n")
    blocks: List[ChatContentBlock] = []
    markdown_buffer: List[str] = []
    formula_buffer: List[str] = []

    def flush_markdown() -> None:
        nonlocal markdown_buffer
        text = "\n".join(markdown_buffer).strip()
        if text:
            blocks.append(ChatContentBlock(type="markdown", content=text))
        markdown_buffer = []

    def flush_formula() -> None:
        nonlocal formula_buffer
        merged = _merge_formula_lines(formula_buffer)
        if merged:
            blocks.append(ChatContentBlock(type="math", content=merged))
        elif formula_buffer:
            markdown_buffer.extend(formula_buffer)
        formula_buffer = []

    index = 0
    while index < len(lines):
        line = lines[index]
        trimmed = line.strip()

        if trimmed.startswith("```"):
            flush_formula()
            flush_markdown()
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_lines.append(lines[index])
                if lines[index].strip().startswith("```"):
                    break
                index += 1
            code_content = "\n".join(code_lines)
            table_content = _extract_table_from_fenced_code_block(code_content)
            if table_content:
                blocks.append(ChatContentBlock(type="table", content=table_content))
            else:
                blocks.append(ChatContentBlock(type="code", content=code_content))
            index += 1
            continue

        if trimmed == "$$":
            flush_formula()
            flush_markdown()
            math_lines: List[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "$$":
                math_lines.append(lines[index])
                index += 1
            math_content = "\n".join(math_lines).strip()
            if math_content:
                blocks.append(ChatContentBlock(type="math", content=math_content))
            index += 1
            continue

        if re.match(r"^<table[\s>]", trimmed, re.IGNORECASE):
            flush_formula()
            flush_markdown()
            table_lines = [line]
            index += 1
            while index < len(lines):
                table_lines.append(lines[index])
                if re.search(r"</table>", lines[index], re.IGNORECASE):
                    break
                index += 1
            blocks.append(ChatContentBlock(type="table", content="\n".join(table_lines)))
            index += 1
            continue

        if _is_table_row(trimmed) and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            flush_formula()
            flush_markdown()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and (_is_table_row(lines[index].strip()) or lines[index].strip() == ""):
                if lines[index].strip():
                    table_lines.append(lines[index])
                index += 1
            blocks.append(ChatContentBlock(type="table", content="\n".join(table_lines)))
            continue

        if trimmed == "":
            if formula_buffer:
                next_non_empty = next((candidate for candidate in lines[index + 1:] if candidate.strip()), "")
                if next_non_empty and _looks_like_formula_line(next_non_empty):
                    index += 1
                    continue
            flush_formula()
            markdown_buffer.append(line)
            index += 1
            continue

        if _looks_like_formula_line(line) or (formula_buffer and _looks_like_formula_line(line)):
            formula_buffer.append(line)
            index += 1
            continue

        flush_formula()
        markdown_buffer.append(line)
        index += 1

    flush_formula()
    flush_markdown()
    return blocks


class SessionManager:
    """
    Manages ChatAgent sessions for different users.
    Each session maintains its own conversation history.
    """

    def __init__(self):
        self._sessions: Dict[str, ChatAgent] = {}
        self._session_metadata: Dict[str, dict] = {}
        self._session_store = RedisSessionStore()
        settings.AGENT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        settings.CHAT_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "")
        return sanitized or "unknown"

    def _get_user_memory_dir(self, username: str) -> Path:
        user_dir = settings.AGENT_MEMORY_DIR / self._sanitize_path_component(username)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_user_session_dir(self, username: str) -> Path:
        user_dir = settings.CHAT_SESSION_DIR / self._sanitize_path_component(username)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_memory_path(self, username: str, session_id: str) -> Path:
        return self._get_user_memory_dir(username) / f"{session_id}.json"

    def _get_session_path(self, username: str, session_id: str) -> Path:
        return self._get_user_session_dir(username) / f"{session_id}.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _normalize_metadata(metadata: dict) -> dict:
        if not metadata:
            return {}

        normalized = dict(metadata)
        normalized["session_id"] = str(normalized.get("session_id") or "")
        normalized["username"] = str(normalized.get("username") or "")
        normalized["title"] = str(normalized.get("title") or "新对话")
        normalized["created_at"] = str(normalized.get("created_at") or SessionManager._now_iso())
        normalized["updated_at"] = str(normalized.get("updated_at") or normalized["created_at"])
        normalized["last_activity"] = str(normalized.get("last_activity") or normalized["updated_at"])
        normalized["message_count"] = int(normalized.get("message_count") or 0)
        normalized["memory_enabled"] = bool(normalized.get("memory_enabled", False))
        return normalized

    def _cache_session_metadata(self, metadata: dict, *, persist: bool = True) -> dict:
        normalized = self._normalize_metadata(metadata)
        session_id = normalized.get("session_id")
        if not session_id:
            return normalized

        self._session_metadata[session_id] = normalized
        if persist:
            self._session_store.upsert_session(normalized)
        return normalized

    def _metadata_from_transcript(
        self,
        username: str,
        session_id: str,
        transcript: dict,
        *,
        memory_enabled: Optional[bool] = None,
    ) -> dict:
        messages = transcript.get("messages", [])
        created_at = transcript.get("created_at") or self._now_iso()
        updated_at = transcript.get("updated_at") or created_at
        return {
            "session_id": session_id,
            "username": username,
            "title": transcript.get("title") or "新对话",
            "created_at": created_at,
            "updated_at": updated_at,
            "last_activity": updated_at,
            "message_count": len(messages),
            "memory_enabled": bool(memory_enabled),
        }

    def _load_session_metadata_from_store(self, session_id: str) -> Optional[dict]:
        cached = self._session_metadata.get(session_id)
        if cached is not None:
            return cached

        metadata = self._session_store.get_session(session_id)
        if metadata is None:
            return None
        return self._cache_session_metadata(metadata, persist=False)

    def _collect_file_backed_sessions(self, username: str, *, sync_to_store: bool = True) -> List[dict]:
        user_dir = self._get_user_session_dir(username)
        sessions: List[dict] = []

        for session_file in user_dir.glob("*.json"):
            try:
                transcript = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Failed to parse session transcript {session_file}: {exc}")
                continue

            metadata = self._metadata_from_transcript(
                username,
                transcript.get("session_id", session_file.stem),
                transcript,
                memory_enabled=bool(self._sessions.get(transcript.get("session_id", session_file.stem))),
            )
            sessions.append(self._cache_session_metadata(metadata, persist=sync_to_store))

        return sessions

    def _load_session_transcript(self, username: str, session_id: str) -> Optional[dict]:
        session_path = self._get_session_path(username, session_id)
        if not session_path.exists():
            return None
        try:
            transcript = json.loads(session_path.read_text(encoding="utf-8"))
            self._cache_session_metadata(
                self._metadata_from_transcript(
                    username,
                    session_id,
                    transcript,
                    memory_enabled=bool(self._sessions.get(session_id)),
                )
            )
            return transcript
        except Exception as exc:
            logger.warning(f"Failed to load session transcript from {session_path}: {exc}")
            return None

    def _save_session_transcript(self, username: str, session_id: str, transcript: dict) -> None:
        session_path = self._get_session_path(username, session_id)
        session_path.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache_session_metadata(
            self._metadata_from_transcript(
                username,
                session_id,
                transcript,
                memory_enabled=bool(self._sessions.get(session_id)),
            )
        )

    def _session_title_from_message(self, message: str) -> str:
        text = (message or "").strip().replace("\n", " ")
        if not text:
            return "新对话"
        return text[:40]

    def _ensure_session_transcript(self, username: str, session_id: str, first_user_message: Optional[str] = None) -> dict:
        existing = self._load_session_transcript(username, session_id)
        if existing is not None:
            return existing

        now = datetime.now().isoformat()
        transcript = {
            "session_id": session_id,
            "username": username,
            "title": self._session_title_from_message(first_user_message or ""),
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._save_session_transcript(username, session_id, transcript)
        return transcript

    def append_transcript_message(
        self,
        username: str,
        session_id: str,
        *,
        role: str,
        content: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        reasoning: Optional[str] = None,
        reasoning_blocks: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, str]]] = None,
        assets: Optional[List[Dict[str, str]]] = None,
        retrieval_traces: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        transcript = self._ensure_session_transcript(
            username,
            session_id,
            first_user_message=content if role == "user" else None,
        )

        if role == "user" and not transcript.get("messages"):
            transcript["title"] = self._session_title_from_message(content)

        transcript["messages"].append(
            {
                "role": role,
                "content": content,
                "blocks": blocks,
                "reasoning": reasoning,
                "reasoning_blocks": reasoning_blocks,
                "sources": sources,
                "assets": assets,
                "retrieval_traces": retrieval_traces,
                "timestamp": datetime.now().isoformat(),
            }
        )
        transcript["updated_at"] = datetime.now().isoformat()
        self._save_session_transcript(username, session_id, transcript)

    def list_sessions(self, username: str) -> List[dict]:
        sessions_by_id: Dict[str, dict] = {}

        for metadata in self._session_store.list_sessions_for_user(username):
            normalized = self._cache_session_metadata(metadata, persist=False)
            sessions_by_id[normalized["session_id"]] = normalized

        for metadata in self._collect_file_backed_sessions(username, sync_to_store=True):
            current = sessions_by_id.get(metadata["session_id"])
            if current is None or str(metadata.get("updated_at") or "") >= str(current.get("updated_at") or ""):
                sessions_by_id[metadata["session_id"]] = metadata

        sessions = list(sessions_by_id.values())
        sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return sessions

    def list_session_ids_for_user(self, username: str) -> List[str]:
        return [session["session_id"] for session in self.list_sessions(username)]

    def get_session_detail(self, username: str, session_id: str) -> Optional[dict]:
        transcript = self._load_session_transcript(username, session_id)
        if transcript is None:
            return None
        if transcript.get("username") and transcript.get("username") != username:
            return None
        return transcript

    def _build_agent_memory(self):
        """
        Build a CAMEL long-term memory for each chat session.

        Falls back to ChatAgent's default memory if the current runtime does not
        expose the required CAMEL memory APIs.
        """
        if not settings.AGENT_MEMORY_ENABLED:
            logger.info("Agent memory disabled by configuration")
            return None

        try:
            from app.dependencies import get_embedding_model
            from app.core.agent_memory import SafeLongtermAgentMemory
            from app.core.model_runtime import build_token_counter
            from camel.memories import (
                ChatHistoryBlock,
                ScoreBasedContextCreator,
                VectorDBBlock,
            )
        except Exception as exc:
            logger.warning(f"CAMEL memory module unavailable, falling back to default memory: {exc}")
            return None

        try:
            context_creator = ScoreBasedContextCreator(
                token_counter=build_token_counter(),
                token_limit=settings.AGENT_MEMORY_TOKEN_LIMIT,
            )
            embedding_model = get_embedding_model()

            memory = SafeLongtermAgentMemory(
                context_creator=context_creator,
                chat_history_block=ChatHistoryBlock(
                    keep_rate=settings.AGENT_MEMORY_KEEP_RATE,
                ),
                vector_db_block=VectorDBBlock(embedding=embedding_model),
                retrieve_limit=settings.AGENT_MEMORY_RETRIEVE_LIMIT,
            )

            logger.info(
                "Initialized CAMEL long-term memory | token_limit={} retrieve_limit={} keep_rate={}",
                settings.AGENT_MEMORY_TOKEN_LIMIT,
                settings.AGENT_MEMORY_RETRIEVE_LIMIT,
                settings.AGENT_MEMORY_KEEP_RATE,
            )
            return memory
        except Exception as exc:
            logger.warning(f"Failed to initialize CAMEL long-term memory, fallback to default memory: {exc}")
            return None

    def get_or_create(self, username: str, session_id: Optional[str] = None) -> Tuple[str, ChatAgent]:
        """
        Get or create a ChatAgent for the given session.

        Args:
            username: Authenticated username that owns the session
            session_id: Optional session ID. If None, creates a new session.

        Returns:
            Tuple of (session_id, ChatAgent)
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        existing_metadata = self.get_session_info(session_id)
        if existing_metadata is None:
            transcript = self._load_session_transcript(username, session_id)
            if transcript is not None:
                existing_metadata = self._cache_session_metadata(
                    self._metadata_from_transcript(username, session_id, transcript),
                    persist=True,
                )
        if existing_metadata and existing_metadata.get("username") != username:
            raise PermissionError(f"Session '{session_id}' does not belong to user '{username}'")

        if session_id not in self._sessions:
            logger.info(f"Creating new chat session: {session_id}")
            self._sessions[session_id] = self._create_chat_agent()
            self._restore_session_memory(username, session_id, self._sessions[session_id])
            if existing_metadata is None:
                existing_metadata = {
                    "session_id": session_id,
                    "username": username,
                    "title": "新对话",
                    "created_at": self._now_iso(),
                    "updated_at": self._now_iso(),
                    "last_activity": self._now_iso(),
                    "message_count": 0,
                    "memory_enabled": bool(getattr(self._sessions[session_id], "memory", None)),
                }
            else:
                existing_metadata = dict(existing_metadata)
                existing_metadata["memory_enabled"] = bool(getattr(self._sessions[session_id], "memory", None))
            self._cache_session_metadata(existing_metadata)

        # Update last activity
        metadata = dict(self.get_session_info(session_id) or {})
        metadata["last_activity"] = self._now_iso()
        metadata["updated_at"] = metadata["last_activity"]
        metadata["memory_enabled"] = bool(getattr(self._sessions[session_id], "memory", None))
        self._cache_session_metadata(metadata)

        return session_id, self._sessions[session_id]

    def _create_chat_agent(self) -> ChatAgent:
        """Create a new ChatAgent instance"""
        from app.core.agent_factory import create_chat_agent

        agent_memory = self._build_agent_memory()
        return create_chat_agent(memory=agent_memory)

    @staticmethod
    def _get_raw_chat_history_record_dicts(chat_agent: ChatAgent) -> Optional[List[dict]]:
        """Get raw chat-history records without vector-retrieval augmentation."""
        memory = getattr(chat_agent, "memory", None)
        if memory is None:
            return None

        for attr_name in ("chat_history_block", "_chat_history_block"):
            history_block = getattr(memory, attr_name, None)
            storage = getattr(history_block, "storage", None)
            if storage is None or not hasattr(storage, "load"):
                continue
            try:
                records = storage.load()
            except Exception:
                continue
            if isinstance(records, list):
                return records

        return None

    @staticmethod
    def _normalize_persisted_memory_records(records: List[dict]) -> List[dict]:
        """Drop persisted system messages and deduplicate records by UUID."""
        normalized: List[dict] = []
        seen_uuids: set[str] = set()

        for record_dict in records:
            if not isinstance(record_dict, dict):
                continue

            record_uuid = str(record_dict.get("uuid") or "").strip()
            if record_uuid and record_uuid in seen_uuids:
                continue
            if record_uuid:
                seen_uuids.add(record_uuid)

            msg = record_dict.get("message", {}) or {}
            role_type = str(msg.get("role_type") or "").strip().lower()
            role_at_backend = str(record_dict.get("role_at_backend") or "").strip().lower()

            if role_type == "system" or role_at_backend == "system":
                continue

            required_keys = ("message", "role_at_backend", "agent_id")
            if not all(key in record_dict for key in required_keys):
                continue

            normalized.append(record_dict)

        return normalized

    def _restore_session_memory(self, username: str, session_id: str, chat_agent: ChatAgent) -> None:
        """Restore persisted memory for an existing session ID if available."""
        if not settings.AGENT_MEMORY_ENABLED:
            logger.info("Agent memory disabled by configuration, skip memory restore")
            return

        memory_path = self._get_memory_path(username, session_id)
        if not memory_path.exists():
            return

        if not hasattr(chat_agent, "memory") or not hasattr(chat_agent.memory, "write_records"):
            logger.warning("ChatAgent does not support memory write_records, skip memory restore")
            return

        try:
            import json
            from camel.memories.records import MemoryRecord

            with open(memory_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()

            records = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue

            if not records:
                return

            if hasattr(chat_agent, "clear_memory"):
                chat_agent.clear_memory()
            elif hasattr(chat_agent.memory, "clear"):
                chat_agent.memory.clear()

            records = self._normalize_persisted_memory_records(records)
            records_to_load = []
            for record_dict in records:
                try:
                    record = MemoryRecord.from_dict(record_dict)
                    records_to_load.append(record)
                except Exception as e:
                    logger.warning(f"Error converting record: {e}")
                    continue

            if records_to_load:
                chat_agent.memory.write_records(records_to_load)
                logger.info(f"Restored {len(records_to_load)} memory records from {memory_path}")
            else:
                logger.info(f"No user/assistant records to restore from {memory_path}")

        except Exception as exc:
            logger.warning(f"Failed to restore agent memory from {memory_path}: {exc}")

    def save_session_memory(self, username: str, session_id: str) -> None:
        """Persist raw chat-history memory, excluding system messages."""
        if not settings.AGENT_MEMORY_ENABLED:
            return

        chat_agent = self._sessions.get(session_id)
        if chat_agent is None:
            return

        memory_path = self._get_memory_path(username, session_id)
        try:
            import json

            raw_history_records = self._get_raw_chat_history_record_dicts(chat_agent)
            if raw_history_records is not None:
                records_to_save = self._normalize_persisted_memory_records(raw_history_records)
            else:
                from camel.types import OpenAIBackendRole

                context_records = chat_agent.memory.retrieve()
                records_to_save = []
                for cr in context_records:
                    if cr.memory_record.role_at_backend == OpenAIBackendRole.SYSTEM:
                        continue
                    records_to_save.append(cr.memory_record.to_dict())
                records_to_save = self._normalize_persisted_memory_records(records_to_save)

            with open(memory_path, 'w', encoding='utf-8') as f:
                for record in records_to_save:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

            logger.debug(f"Saved {len(records_to_save)} raw memory records (excluding system) to {memory_path}")
        except Exception as exc:
            logger.warning(f"Failed to save agent memory to {memory_path}: {exc}")

    def clear_session(self, username: str, session_id: str) -> bool:
        """
        Clear a session and its ChatAgent.

        Args:
            session_id: Session ID to clear

        Returns:
            True if session was cleared, False if not found
        """
        metadata = self.get_session_info(session_id)
        transcript = self._load_session_transcript(username, session_id)
        if metadata and metadata.get("username") != username:
            logger.warning(
                "User '{}' attempted to clear session '{}' owned by '{}'",
                username,
                session_id,
                metadata.get("username"),
            )
            return False
        if transcript and transcript.get("username") and transcript.get("username") != username:
            logger.warning(
                "User '{}' attempted to clear persisted session '{}' owned by '{}'",
                username,
                session_id,
                transcript.get("username"),
            )
            return False

        if session_id in self._sessions:
            chat_agent = self._sessions[session_id]
            if hasattr(chat_agent, "memory") and hasattr(chat_agent.memory, "clear"):
                try:
                    chat_agent.memory.clear()
                except Exception as exc:
                    logger.warning(f"Failed to clear chat memory for session {session_id}: {exc}")
            del self._sessions[session_id]
            self._session_metadata.pop(session_id, None)
            self._session_store.delete_session(username, session_id)
            with suppress(FileNotFoundError):
                self._get_memory_path(username, session_id).unlink()
            with suppress(FileNotFoundError):
                self._get_session_path(username, session_id).unlink()
            logger.info(f"Session cleared: {session_id}")
            return True

        if transcript is not None:
            self._session_metadata.pop(session_id, None)
            self._session_store.delete_session(username, session_id)
            with suppress(FileNotFoundError):
                self._get_memory_path(username, session_id).unlink()
            with suppress(FileNotFoundError):
                self._get_session_path(username, session_id).unlink()
            logger.info(f"Persisted session cleared: {session_id}")
            return True
        return False

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """Get session metadata"""
        return self._load_session_metadata_from_store(session_id)

    def increment_message_count(self, username: str, session_id: str):
        """Increment message count for a session"""
        metadata = self.get_session_info(session_id)
        if metadata is None:
            transcript = self._load_session_transcript(username, session_id)
            if transcript is not None:
                metadata = self._metadata_from_transcript(username, session_id, transcript)

        if not metadata or metadata.get("username") != username:
            return

        metadata = dict(metadata)
        metadata["message_count"] = int(metadata.get("message_count") or 0) + 1
        metadata["last_activity"] = self._now_iso()
        metadata["updated_at"] = metadata["last_activity"]
        self._cache_session_metadata(metadata)


class ChatService:
    """Chat service handling streaming responses"""

    TOKEN_LIMIT_ERROR_MARKERS = (
        "maximum context length",
        "context length",
        "max_tokens_exceeded",
        "input tokens",
        "token limit",
    )
    FACTUAL_QUERY_PATTERNS = (
        "是什么",
        "什么是",
        "谁是",
        "定义",
        "含义",
        "概念",
        "解释",
        "介绍",
        "作用",
        "用途",
        "区别",
        "联系",
        "参数",
        "是否",
        "多少",
        "几种",
        "哪些",
        "哪几",
        "哪一条",
        "哪一项",
        "哪一个",
        "什么意思",
        "是什么原因",
        "为什么",
        "原因",
        "要求",
        "依据",
        "标准",
        "规范",
        "流程",
        "步骤",
        "条件",
        "范围",
        "适用",
        "适用于",
        "包括",
        "包含",
        "注意事项",
        "职责",
        "负责",
        "区别",
        "分类",
        "类型",
        "阈值",
        "上限",
        "下限",
        "比例",
        "计算",
        "公式",
        "怎么规定",
        "如何规定",
        "怎么要求",
        "如何要求",
    )
    FACTUAL_QUERY_REGEXES = (
        r"^(什么|谁|哪[个些几条项种类]|多少|几).*[？?]?$",
        r".*(是什么|什么意思|指什么|属于什么).*[？?]?$",
        r".*(是否|能否|可否|有没有).*[？?]?$",
        r".*(要求|规定|依据|标准|规范|流程|步骤|条件|范围|职责|作用|用途|参数|区别|原因).*[？?]?$",
        r".*(怎么规定|如何规定|怎么要求|如何要求|怎么计算|如何计算).*[？?]?$",
    )

    def __init__(self):
        self.session_manager = SessionManager()
        self._intent_router: Optional[ChatAgent] = None
        self._search_rewriter: Optional[ChatAgent] = None

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 3)

    def _log_context_budget(self, chat_agent: ChatAgent, user_message: str):
        """
        Roughly estimate prompt size. This is not exact token counting, but it is
        sufficient to identify whether growth comes from history or retrieval.
        """
        if not settings.CHAT_CONTEXT_BUDGET_LOG_ENABLED:
            return
        try:
            memory_context = ""
            if hasattr(chat_agent, "memory") and hasattr(chat_agent.memory, "get_context"):
                context = chat_agent.memory.get_context()
                if isinstance(context, tuple):
                    memory_context = str(context[0])
                elif isinstance(context, str):
                    memory_context = context
                else:
                    memory_context = str(context)

            system_prompt = ""
            if hasattr(chat_agent, "system_message") and hasattr(chat_agent.system_message, "content"):
                system_prompt = chat_agent.system_message.content or ""

            system_tokens = self._estimate_tokens(system_prompt)
            history_tokens = self._estimate_tokens(memory_context)
            user_tokens = self._estimate_tokens(user_message)
            total_tokens = system_tokens + history_tokens + user_tokens

            logger.info(
                "Context budget estimate | system={} history={} user={} total={}",
                system_tokens,
                history_tokens,
                user_tokens,
                total_tokens,
            )
        except Exception as exc:
            logger.warning(f"Failed to estimate context budget: {exc}")

    def _is_token_limit_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in self.TOKEN_LIMIT_ERROR_MARKERS)

    def _is_factual_query_fallback(self, message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False
        if any(pattern in text for pattern in self.FACTUAL_QUERY_PATTERNS):
            return True
        return any(re.search(pattern, text) for pattern in self.FACTUAL_QUERY_REGEXES)

    def _get_intent_router(self) -> ChatAgent:
        if self._intent_router is None:
            from app.core.model_runtime import backend_model

            self._intent_router = ChatAgent(
                system_message=BaseMessage.make_system_message(
                    content=(
                        "你是一个对话路由器。你的任务是判断当前用户问题在本轮回答前是否必须强制检索知识库。"
                        "如果问题需要基于文档、标准、流程、定义、参数、条件、范围、职责、原因、区别、是否、多少等事实性内容回答，"
                        "则 needs_search=true。"
                        "如果只是寒暄、闲聊、改写、润色、总结用户刚刚提供的文本、表达偏好、纯主观建议，"
                        "则 needs_search=false。"
                        "必须结合最近对话上下文理解代词和追问。"
                    ),
                ),
                model=backend_model(
                    model_name=settings.INTENT_ROUTER_MODEL_NAME,
                    temperature=settings.INTENT_ROUTER_TEMPERATURE,
                    top_p=settings.INTENT_ROUTER_TOP_P,
                    max_tokens=settings.INTENT_ROUTER_MAX_TOKENS,
                ),
                tools=[],
                summarize_threshold=None,
            )
        else:
            self._intent_router.reset()
        return self._intent_router

    def _get_search_rewriter(self) -> ChatAgent:
        if self._search_rewriter is None:
            from app.core.model_runtime import backend_model

            self._search_rewriter = ChatAgent(
                system_message=BaseMessage.make_system_message(
                    content=(
                        "你是检索改写器。任务：结合上下文，把追问改写成检索query。"
                        "必须补全代词/简称/省略的主体（标准、文件、设备、表格等）。"
                        "expanded_queries≤2条，仅用于别名/表号/同义词，禁无关扩展。"
                        "只输出一行JSON，格式：{\"query\":\"...\",\"intent_description\":\"...\",\"expanded_queries\":[],\"referent\":\"...\",\"reason\":\"...\"}"
                        "禁止输出任何其他内容。query≤32字，intent_description≤80字，reason≤20字。"
                    ),
                ),
                model=backend_model(
                    model_name=settings.SEARCH_REWRITER_MODEL_NAME,
                    temperature=settings.SEARCH_REWRITER_TEMPERATURE,
                    top_p=settings.SEARCH_REWRITER_TOP_P,
                    max_tokens=settings.SEARCH_REWRITER_MAX_TOKENS,
                ),
                tools=[],
                summarize_threshold=None,
            )
        else:
            self._search_rewriter.reset()
        return self._search_rewriter

    def _route_requires_search(self, username: str, session_id: str, message: str) -> bool:
        transcript = self.session_manager.get_session_detail(username, session_id) or {}
        recent_messages = transcript.get("messages", [])[-4:]
        context_lines: List[str] = []
        for item in recent_messages:
            role = "用户" if item.get("role") == "user" else "助手"
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content:
                context_lines.append(f"{role}: {content[:300]}")

        router_prompt = (
            "最近对话上下文：\n"
            + ("\n".join(context_lines) if context_lines else "无")
            + f"\n\n当前用户问题：{message}\n\n"
            "请判断本轮回答前是否必须先强制检索知识库。"
        )

        try:
            router = self._get_intent_router()
            response = router.step(router_prompt, response_format=IntentRoutingDecision)
            parsed = None
            if hasattr(response, "msgs") and response.msgs:
                parsed = getattr(response.msgs[-1], "parsed", None)
            if parsed is None:
                logger.warning("Intent router returned no structured result, fallback to regex")
                return self._is_factual_query_fallback(message)

            needs_search = bool(parsed.needs_search)
            logger.info(
                "Intent router decision | session={} needs_search={} confidence={} reason={}",
                session_id,
                needs_search,
                getattr(parsed, "confidence", 0.0),
                getattr(parsed, "reason", ""),
            )
            return needs_search
        except Exception as exc:
            logger.warning(f"Intent router failed, fallback to regex: {exc}")
            return self._is_factual_query_fallback(message)

    def _build_search_rewrite_plan(
        self,
        username: str,
        session_id: str,
        message: str,
    ) -> SearchRewritePlan:
        transcript = self.session_manager.get_session_detail(username, session_id) or {}
        recent_messages = transcript.get("messages", [])[-6:]
        context_lines: List[str] = []
        for item in recent_messages:
            role = "用户" if item.get("role") == "user" else "助手"
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content:
                context_lines.append(f"{role}: {content[:400]}")

        planner_prompt = (
            "上下文：\n"
            + ("\n".join(context_lines) if context_lines else "无")
            + f"\n当前问题：{message}\n\n"
            "任务：结合上下文补全代词/省略主体，输出检索query。\n"
            "严格只输出一行JSON，不要任何解释或对话：\n"
            "{\"query\":\"关键词\",\"intent_description\":\"完整意图\",\"expanded_queries\":[\"补充词\"],\"referent\":\"主体\",\"reason\":\"简述\"}\n"
            "限制：query≤32字，intent_description≤80字，expanded_queries最多2条。"
        )

        try:
            planner = self._get_search_rewriter()
            # 不使用 response_format，避免结构化输出的长度限制问题
            response = planner.step(planner_prompt)
            raw_content = ""
            if hasattr(response, "msgs") and response.msgs:
                raw_content = str(response.msgs[-1].content or "")

            # 手动解析 JSON
            import json
            import re
            # 提取 JSON 内容（可能被包裹在其他文本中）
            json_match = re.search(r"\{[\s\S]*\}", raw_content)
            if not json_match:
                raise ValueError(f"No JSON found in response: {raw_content[:200]}")
            json_str = json_match.group()
            data = json.loads(json_str)

            plan = SearchRewritePlan(
                query=str(data.get("query", ""))[:50],
                intent_description=str(data.get("intent_description", ""))[:100],
                expanded_queries=list(data.get("expanded_queries", []))[:2],
                referent=str(data.get("referent", ""))[:50],
                reason=str(data.get("reason", ""))[:30],
            )
            logger.info(
                "Search rewrite plan | session={} referent={} query={} expanded={}",
                session_id,
                plan.referent,
                plan.query,
                len(plan.expanded_queries),
            )
            return plan
        except Exception as exc:
            logger.warning(f"Search rewrite plan failed, fallback to heuristic rewrite: {exc}")
            # 改进 fallback：从最近对话中提取主题
            referent = ""
            subject_keywords = []

            # 从最近 assistant 回复中提取关键主体
            for item in reversed(recent_messages):
                content = str(item.get("content") or "").replace("\n", " ").strip()
                if not content:
                    continue
                # 提取可能的主体词（标准名、设备名等）
                import re
                # 匹配标准号如 GB/T 6451-2015, DL/T 5153-2014 等
                standards = re.findall(r'[A-Z]+/T\s*\d+[-\d]*', content)
                # 匹配中文主体词（变压器、短路阻抗等）
                subjects = re.findall(r'[\u4e00-\u9fff]{2,8}(?:标准|参数|表格|规程|规范|规定)', content)
                if standards:
                    subject_keywords.extend(standards[:2])
                if subjects:
                    subject_keywords.extend(subjects[:2])
                if item.get("role") == "user" and not referent:
                    referent = content[:60]
                if subject_keywords:
                    break

            # 判断是否是追问（消息短或包含追问词）
            followup_tokens = ("表格", "表", "那些", "相关", "一些", "更多", "详细", "具体", "给出", "提供", "列出", "显示")
            is_followup = len(message) < 15 or any(token in message for token in followup_tokens)

            if is_followup and subject_keywords:
                # 追问且有主题，合并主题和当前问题
                combined_subject = " ".join(subject_keywords[:3])
                query = self._keywordize_query(f"{combined_subject} {message}")
                intent_description = f"{combined_subject}。追问：{message}"
            elif referent and any(token in message for token in ("它", "这个", "这个规范", "该规范", "该标准", "涉及", "这些", "那些", "相关")):
                query = self._keywordize_query(f"{referent} {message}")
                intent_description = f"{referent}。当前追问：{message}"
            else:
                query = self._keywordize_query(message)
                intent_description = message
            return SearchRewritePlan(
                query=query,
                intent_description=intent_description,
                expanded_queries=[],
                referent=referent or " ".join(subject_keywords[:2]),
                reason="fallback_heuristic",
            )

    @staticmethod
    def _keywordize_query(message: str) -> str:
        text = re.sub(r"[^\w\u4e00-\u9fff%./-]+", " ", (message or "").strip())
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        stopwords = {"请问", "一下", "这个", "那个", "什么", "是", "的", "了", "吗", "呢", "呀", "其", "它", "该"}
        terms = [term for term in text.split(" ") if term and term not in stopwords]
        return " ".join(terms[:8]) or text[:80]

    @staticmethod
    def _is_table_or_numeric_query(message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False

        table_hints = (
            "表", "表格", "表中", "表里", "列表", "清单", "汇总", "统计",
            "参数", "参数表", "标准值", "数值", "取值", "数据", "阻抗",
            "容量", "损耗", "电压", "电流", "系数", "百分比", "等级",
        )
        numeric_re = re.compile(
            r"\d+(?:\.\d+)?\s*(?:kV|V|A|mA|MW|kW|W|Hz|%|℃|°C|mm|cm|m|km|kg|t|MPa|kPa|年|月|日|h|min|s|次|项|条|章)?",
            re.IGNORECASE,
        )
        return any(token in text for token in table_hints) or bool(numeric_re.search(text))

    @classmethod
    def _build_gap_focused_queries(
        cls,
        primary_query: str,
        intent_description: str,
        referent: str = "",
    ) -> List[str]:
        """
        Add a few high-signal follow-up retrieval queries for table/numeric turns.
        These queries target missing table bodies / standard values instead of
        repeating the same semantic query.
        """
        base = " ".join(part for part in (referent.strip(), primary_query.strip()) if part).strip()
        if not base:
            base = intent_description.strip()
        if not cls._is_table_or_numeric_query(base or intent_description):
            return []

        candidates: List[str] = []
        has_standard = bool(re.search(r"[A-Z]+/T\s*\d+[-\d]*", base or intent_description))
        has_table = any(token in (base or intent_description) for token in ("表", "表格", "表中", "表里"))

        if has_standard:
            candidates.append(f"{base} 标准值")
            candidates.append(f"{base} 表格")
        if not has_table:
            candidates.append(f"{base} 参数表")
        candidates.append(f"{base} 数值")

        normalized: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            query = cls._keywordize_query(candidate)
            if not query or query == primary_query or query in seen:
                continue
            seen.add(query)
            normalized.append(query)
        return normalized[:2]

    def _get_factual_evidence_budget(self, message: str) -> int:
        budget = settings.FACTUAL_EVIDENCE_MAX_CHARS
        if self._is_table_or_numeric_query(message):
            return max(budget, 12000)
        return budget

    def _build_factual_prompt_with_evidence(self, message: str, evidence: str) -> str:
        return (
            "这是事实性问题。后端已经先行检索了一批候选证据。"
            "你必须优先基于这些证据回答，但这些证据不是唯一来源。"
            "如果现有证据不足以回答完整问题，尤其缺少表格正文、参数值、标准值、表号、范围、条件时，"
            "你必须继续调用 `search_database` 做补充检索，而不是直接下结论说查不到。"
            "只有在继续检索后仍然没有获得足够证据时，才能明确说明知识库中未找到或证据不足；"
            "禁止脱离检索结果补充常识。\n\n"
            f"用户问题：{message}\n\n"
            f"本轮检索结果：\n{evidence}"
        )

    @staticmethod
    def _truncate_for_prompt(text: str, max_chars: int) -> str:
        if not text or len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n...[检索证据过长，已截断]"

    def _build_fallback_compact_summary(self, transcript_messages: List[dict]) -> str:
        recent_messages = transcript_messages[-6:]
        lines = [
            "[CONTEXT_SUMMARY] 以下是此前对话的降级压缩摘要，仅用于延续上下文。",
            "事实性结论仍需在本轮重新调用 search_database 验证。",
            "",
        ]
        for item in recent_messages:
            role = "用户" if item.get("role") == "user" else "助手"
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if not content:
                continue
            lines.append(f"{role}: {content[:400]}")
        summary = "\n".join(lines).strip()
        return self._truncate_for_prompt(summary, 2400)

    def _rebuild_session_memory_from_transcript(
        self,
        username: str,
        session_id: str,
        chat_agent: ChatAgent,
        *,
        reason: str,
    ) -> bool:
        transcript = self.session_manager.get_session_detail(username, session_id)
        if not transcript:
            return False

        messages = transcript.get("messages", [])
        if not messages:
            return False

        keep_count = max(0, settings.AGENT_COMPACT_KEEP_RECENT_MESSAGES)
        preserved_messages = messages[-keep_count:] if keep_count > 0 else []
        summary_text = self._build_fallback_compact_summary(messages[:-keep_count] if keep_count > 0 else messages)
        if not summary_text:
            return False

        try:
            chat_agent.clear_memory()
            chat_agent.update_memory(
                BaseMessage.make_assistant_message(
                    role_name="assistant",
                    content=summary_text,
                ),
                OpenAIBackendRole.ASSISTANT,
            )

            for item in preserved_messages:
                role = item.get("role")
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                if role == "user":
                    chat_agent.update_memory(
                        BaseMessage.make_user_message(
                            role_name="user",
                            content=self._truncate_for_prompt(content, 1200),
                        ),
                        OpenAIBackendRole.USER,
                    )
                else:
                    reasoning = str(item.get("reasoning") or "").strip()
                    assistant_content = self._truncate_for_prompt(content, 1200)
                    if reasoning:
                        assistant_content = (
                            f"{assistant_content}\n\n[Reasoning]\n"
                            f"{self._truncate_for_prompt(reasoning, 800)}"
                        )
                    chat_agent.update_memory(
                        BaseMessage.make_assistant_message(
                            role_name="assistant",
                            content=assistant_content,
                        ),
                        OpenAIBackendRole.ASSISTANT,
                    )

            self.session_manager.save_session_memory(username, session_id)
            logger.info(
                "Rebuilt session memory from transcript | session={} user={} reason={}",
                session_id,
                username,
                reason,
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to rebuild session memory from transcript for {session_id}: {exc}")
            return False

    def _force_search_evidence(self, username: str, session_id: str, message: str) -> Optional[str]:
        try:
            from app.dependencies import get_database_toolkit

            toolkit = get_database_toolkit()
            plan = self._build_search_rewrite_plan(username, session_id, message)
            candidate_queries: List[Tuple[str, str]] = []

            primary_query = (plan.query or "").strip()
            primary_intent = (plan.intent_description or message).strip()
            if primary_query:
                candidate_queries.append((primary_query, primary_intent))

            for extra_query in plan.expanded_queries[:2]:
                normalized = (extra_query or "").strip()
                if not normalized:
                    continue
                if normalized == primary_query:
                    continue
                if any(normalized == existing_query for existing_query, _ in candidate_queries):
                    continue
                candidate_queries.append((normalized, primary_intent))

            for gap_query in self._build_gap_focused_queries(
                primary_query=primary_query,
                intent_description=primary_intent,
                referent=plan.referent,
            ):
                if any(gap_query == existing_query for existing_query, _ in candidate_queries):
                    continue
                candidate_queries.append((gap_query, primary_intent))

            if not candidate_queries:
                heuristic_query = self._keywordize_query(message)
                if heuristic_query:
                    candidate_queries.append((heuristic_query, message))

            evidence_parts: List[str] = []
            seen_keys: set = set()  # 本次三次搜索内去重
            for idx, (query, intent_description) in enumerate(candidate_queries[:3], start=1):
                evidence = toolkit.search_database(
                    query=query,
                    intent_description=intent_description,
                    seen_keys=seen_keys,
                )
                normalized = (evidence or "").strip()
                if not normalized or normalized == "No results from the vector database.":
                    continue
                if normalized == "No new results from the vector database in this turn.":
                    continue
                evidence_parts.append(f"[检索 {idx}] query={query}\n{normalized}")

            if not evidence_parts:
                return (
                    "当前知识库检索未返回有效结果。你必须明确说明未找到相关信息，"
                    "不要基于常识自行作答。"
                )
            merged_evidence = "\n\n".join(evidence_parts)
            return self._truncate_for_prompt(
                merged_evidence,
                self._get_factual_evidence_budget(message),
            )
        except Exception as exc:
            logger.warning(f"Forced factual search failed: {exc}")
            return (
                "知识库检索在本轮执行失败。你必须明确说明检索失败或证据不足，"
                "不要基于历史记忆或常识自行作答。"
            )

    def _backfill_turn_refs(self, username: str, session_id: str, message: str) -> None:
        """Run lightweight retrieval only to populate per-turn source/asset refs."""
        try:
            from app.dependencies import get_database_toolkit

            toolkit = get_database_toolkit()
            plan = self._build_search_rewrite_plan(username, session_id, message)
            candidate_queries: List[Tuple[str, str]] = []

            primary_query = (plan.query or "").strip()
            primary_intent = (plan.intent_description or message).strip()
            if primary_query:
                candidate_queries.append((primary_query, primary_intent))

            for extra_query in plan.expanded_queries[:1]:
                normalized = (extra_query or "").strip()
                if not normalized:
                    continue
                if any(normalized == existing_query for existing_query, _ in candidate_queries):
                    continue
                candidate_queries.append((normalized, primary_intent))

            if not candidate_queries:
                heuristic_query = self._keywordize_query(message)
                if heuristic_query:
                    candidate_queries.append((heuristic_query, message))

            for query, intent_description in candidate_queries[:2]:
                toolkit.search_database(
                    query=query,
                    intent_description=intent_description,
                )

                if toolkit.get_turn_source_refs() or toolkit.get_turn_asset_refs():
                    logger.info(
                        "Backfilled turn refs | session={} query='{}' sources={} assets={}",
                        session_id,
                        query,
                        len(toolkit.get_turn_source_refs()),
                        len(toolkit.get_turn_asset_refs()),
                    )
                    return

            logger.info("Backfill turn refs produced no metadata | session={}", session_id)
        except Exception as exc:
            logger.warning(f"Failed to backfill turn refs for session {session_id}: {exc}")

    def _session_needs_compaction(self, username: str, session_id: str) -> bool:
        if not settings.AGENT_COMPACT_ENABLED:
            return False

        transcript = self.session_manager.get_session_detail(username, session_id)
        if not transcript:
            return False

        messages = transcript.get("messages", [])
        if len(messages) >= settings.AGENT_COMPACT_TRIGGER_MESSAGES:
            return True

        total_chars = sum(len(str(item.get("content", ""))) for item in messages)
        return total_chars >= settings.AGENT_COMPACT_TRIGGER_CHARS

    def _compact_session(
        self,
        username: str,
        session_id: str,
        chat_agent: ChatAgent,
        reason: str,
    ) -> bool:
        if not settings.AGENT_COMPACT_ENABLED:
            return False

        transcript = self.session_manager.get_session_detail(username, session_id)
        if not transcript:
            return False

        messages = transcript.get("messages", [])
        keep_count = max(0, settings.AGENT_COMPACT_KEEP_RECENT_MESSAGES)
        if len(messages) <= keep_count + 2:
            return False

        summary_text = ""
        try:
            summary_result = chat_agent.summarize(include_summaries=True)
            summary_text = (summary_result or {}).get("summary", "").strip()
        except Exception as exc:
            logger.warning(f"Failed to summarize session {session_id} before compaction: {exc}")
            summary_text = self._build_fallback_compact_summary(messages)
        if not summary_text:
            summary_text = self._build_fallback_compact_summary(messages)
        if not summary_text:
            logger.warning(f"Session {session_id} compaction skipped because summary is empty")
            return False

        preserved_messages = messages[-keep_count:] if keep_count > 0 else []

        try:
            chat_agent.clear_memory()
            compact_summary = (
                "[CONTEXT_SUMMARY] 以下是此前对话的压缩摘要，用于延续上下文；"
                "其中事实性结论仍需在本轮重新调用 search_database 验证。\n\n"
                f"{summary_text}"
            )
            chat_agent.update_memory(
                BaseMessage.make_assistant_message(
                    role_name="assistant",
                    content=compact_summary,
                ),
                OpenAIBackendRole.ASSISTANT,
            )

            for item in preserved_messages:
                role = item.get("role")
                content = item.get("content") or ""
                if not content:
                    continue

                if role == "user":
                    chat_agent.update_memory(
                        BaseMessage.make_user_message(
                            role_name="user",
                            content=content,
                        ),
                        OpenAIBackendRole.USER,
                    )
                else:
                    assistant_content = content
                    reasoning = item.get("reasoning")
                    if reasoning:
                        assistant_content = f"{assistant_content}\n\n[Reasoning]\n{reasoning}"
                    chat_agent.update_memory(
                        BaseMessage.make_assistant_message(
                            role_name="assistant",
                            content=assistant_content,
                        ),
                        OpenAIBackendRole.ASSISTANT,
                    )

            transcript["compaction"] = {
                "last_compacted_at": datetime.now().isoformat(),
                "reason": reason,
                "preserved_recent_messages": keep_count,
            }
            self.session_manager._save_session_transcript(username, session_id, transcript)
            self.session_manager.save_session_memory(username, session_id)
            logger.info(
                "Compacted session {} for user {} | reason={} preserved_messages={}",
                session_id,
                username,
                reason,
                keep_count,
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to compact session {session_id}: {exc}")
            return False

    @staticmethod
    def _build_new_chat_required_message() -> str:
        return (
            "当前对话累计上下文已经超过模型可处理上限，即使执行压缩后仍然过长。"
            "请点击“新对话”后继续提问；如果需要延续上下文，请在新对话里简要说明上一轮结论或目标。"
        )

    def stream_chat(
        self,
        message: str,
        username: str,
        session_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Stream chat response as SSE events.

        Args:
            message: User message
            username: Authenticated username
            session_id: Optional session ID

        Yields:
            SSE formatted strings
        """
        try:
            # Get or create session
            session_id, chat_agent = self.session_manager.get_or_create(username, session_id)
            from app.dependencies import get_database_toolkit
            database_toolkit = get_database_toolkit()
            database_toolkit.begin_turn()

            self.session_manager.append_transcript_message(
                username,
                session_id,
                role="user",
                content=message,
            )

            # Increment message count
            self.session_manager.increment_message_count(username, session_id)

            if self._session_needs_compaction(username, session_id):
                rebuilt = self._rebuild_session_memory_from_transcript(
                    username,
                    session_id,
                    chat_agent,
                    reason="pre_step_rebuild",
                )
                if not rebuilt:
                    self._compact_session(
                        username,
                        session_id,
                        chat_agent,
                        reason="proactive_threshold",
                    )

            self._log_context_budget(chat_agent, message)

            # Send session ID first
            yield self._format_message_sse("session", {"session_id": session_id})

            # Stream response
            full_reasoning = ""
            full_response = ""
            retry_after_compact = True
            needs_forced_search = self._route_requires_search(username, session_id, message)
            factual_evidence = self._force_search_evidence(username, session_id, message) if needs_forced_search else None
            agent_message = (
                self._build_factual_prompt_with_evidence(message, factual_evidence)
                if factual_evidence is not None
                else message
            )

            while True:
                try:
                    response = chat_agent.step(agent_message)

                    for chunk_response in response:
                        if hasattr(chunk_response, 'msgs') and len(chunk_response.msgs) > 0:
                            msg = chunk_response.msgs[0]

                            # Handle reasoning content
                            reasoning_text = self._extract_reasoning_text(msg)
                            if reasoning_text:

                                # Filter tool-related content
                                if not self._is_tool_content(reasoning_text):
                                    if reasoning_text.startswith(full_reasoning):
                                        full_reasoning = reasoning_text
                                    else:
                                        full_reasoning += reasoning_text

                                    yield self._format_message_sse("reasoning", {
                                        "content": reasoning_text,
                                    })

                            # Handle response content
                            content_text = msg.content
                            if content_text and not self._is_tool_content(content_text):
                                if content_text.startswith(full_response):
                                    full_response = content_text
                                else:
                                    full_response += content_text

                                yield self._format_message_sse("content", {
                                    "content": content_text,
                                })
                    break
                except Exception as exc:
                    if retry_after_compact and self._is_token_limit_error(exc):
                        logger.warning(
                            "Token limit hit for session {}. Compacting and retrying once.",
                            session_id,
                        )
                        compacted = self._compact_session(
                            username,
                            session_id,
                            chat_agent,
                            reason="token_limit_retry",
                        )
                        if compacted:
                            retry_after_compact = False
                            full_reasoning = ""
                            full_response = ""
                            continue
                    if self._is_token_limit_error(exc):
                        logger.warning(
                            "Token limit persists for session {} after compaction. Asking user to start a new chat.",
                            session_id,
                        )
                        full_response = self._build_new_chat_required_message()
                        full_reasoning = ""
                        break
                    raise

            # Get final content if needed
            if not full_response:
                if hasattr(response, 'msg') and hasattr(response.msg, 'content'):
                    full_response = response.msg.content
                elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                    full_response = response.msgs[-1].content
                else:
                    full_response = "抱歉，我无法生成回复。"

            if not full_reasoning:
                if hasattr(response, 'msg'):
                    full_reasoning = self._extract_reasoning_text(response.msg)
                elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                    full_reasoning = self._extract_reasoning_text(response.msgs[-1])

            raw_full_response = full_response

            # Send done event
            response_blocks = [block.model_dump() for block in _build_content_blocks(full_response)]
            reasoning_blocks = [block.model_dump() for block in _build_content_blocks(full_reasoning)] if full_reasoning else None
            source_refs = self._collect_turn_source_refs(raw_full_response)
            asset_refs = self._collect_turn_asset_refs(raw_full_response, source_refs=source_refs)
            if not source_refs and not asset_refs:
                self._backfill_turn_refs(username, session_id, message)
                source_refs = self._collect_turn_source_refs(raw_full_response)
                asset_refs = self._collect_turn_asset_refs(raw_full_response, source_refs=source_refs)
            retrieval_traces = self._collect_turn_retrieval_traces()
            logger.info(
                "Chat done payload | session={} sources={} assets={} traces={}",
                session_id,
                len(source_refs),
                len(asset_refs),
                len(retrieval_traces),
            )

            # 将 sources 注入到正文末尾，作为特殊区块，前端解析后渲染超链接
            if source_refs:
                sources_block = self._build_sources_block(source_refs)
                full_response_with_sources = full_response + "\n\n" + sources_block
            else:
                full_response_with_sources = full_response

            # 保存到历史记录时也包含 sources block
            self.session_manager.append_transcript_message(
                username,
                session_id,
                role="assistant",
                content=full_response_with_sources,
                blocks=response_blocks,
                reasoning=full_reasoning or None,
                reasoning_blocks=reasoning_blocks,
                sources=source_refs,
                assets=asset_refs,
                retrieval_traces=retrieval_traces or None,
            )
            self.session_manager.save_session_memory(username, session_id)

            yield self._format_message_sse("done", {
                "reasoning": full_reasoning,
                "reasoning_blocks": reasoning_blocks,
                "content": full_response_with_sources,
                "blocks": response_blocks,
                "session_id": session_id,
                "sources": source_refs,
                "assets": asset_refs,
                "retrieval_traces": retrieval_traces,
            })

        except Exception as e:
            if self._is_token_limit_error(e):
                logger.warning(f"Top-level token limit fallback for session {session_id if 'session_id' in locals() else 'unknown'}")
                yield self._format_message_sse("done", {
                    "reasoning": "",
                    "reasoning_blocks": None,
                    "content": self._build_new_chat_required_message(),
                    "blocks": [block.model_dump() for block in _build_content_blocks(self._build_new_chat_required_message())],
                    "session_id": session_id if 'session_id' in locals() else None,
                    "sources": [],
                    "assets": [],
                    "retrieval_traces": [],
                })
                return
            logger.exception(f"Chat streaming error: {e}")
            yield self._format_error_sse(str(e))
        finally:
            with suppress(Exception):
                from app.dependencies import get_database_toolkit
                get_database_toolkit().end_turn()

    def _is_tool_content(self, text: str) -> bool:
        """Check if content is tool-related (should be filtered)"""
        if not text:
            return False
        tool_markers = ["Tool Execution:", "Tool Result:", "Function Call:"]
        return any(marker in text for marker in tool_markers)

    def _extract_reasoning_text(self, msg: Any) -> str:
        """
        Extract reasoning text from model message objects.

        vLLM / OpenAI-compatible providers have used different field names
        across versions, including `reasoning_content` and `reasoning`.
        Keep both for backward compatibility.
        """
        if msg is None:
            return ""

        for field_name in ("reasoning", "reasoning_content"):
            value = None
            if isinstance(msg, dict):
                value = msg.get(field_name)
            elif hasattr(msg, field_name):
                value = getattr(msg, field_name)

            reasoning_text = self._stringify_reasoning_value(value)
            if reasoning_text:
                return reasoning_text

        return ""

    @staticmethod
    def _stringify_reasoning_value(value: Any) -> str:
        """Normalize reasoning payloads from multiple provider formats."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            for key in ("text", "content", "reasoning"):
                nested = value.get(key)
                if isinstance(nested, str) and nested:
                    return nested
            return ""

        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                normalized = ChatService._stringify_reasoning_value(item)
                if normalized:
                    parts.append(normalized)
            return "".join(parts)

        return str(value)

    @staticmethod
    def _format_message_sse(msg_type: str, data: dict) -> str:
        """Format data as a unified SSE message event.

        All business events use ``event: message`` and are distinguished by
        the ``type`` field inside the JSON payload.  This makes the frontend
        parser simpler – it only needs to listen for one SSE event name.
        """
        payload = {"type": msg_type, **data}
        return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def _format_error_sse(message: str) -> str:
        """Format an error as an SSE error event."""
        return f"event: error\ndata: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _extract_sources(content: str) -> List[str]:
        """Extract source file names from the response content."""
        sources: List[str] = []
        seen: set = set()
        lines = (content or "").splitlines()

        def add_source(raw: str) -> None:
            src = (raw or "").strip().strip('《》').strip('"').strip("'")
            src = re.sub(r'^[\-*•·●▪◦‣]+\s*', '', src)
            src = re.sub(r'^\d+\s*[.、)\]]\s*', '', src)
            src = re.sub(
                r'[\s（(【\[](?:第\s*\d+(?:\.\d+){0,6}\s*(?:条|款|项|节|章)?|表\s*[A-Za-z]?\d+(?:[-—]\d+)?|图\s*[A-Za-z]?\d+(?:[-—]\d+)?|附录\s*[A-Za-z0-9一二三四五六七八九十]+).*$',
                '',
                src,
                flags=re.IGNORECASE,
            ).strip(" \t\r\n,，;；:：-—")
            if not src or src in seen:
                return
            seen.add(src)
            sources.append(src)

        for index, line in enumerate(lines):
            match = re.search(r'来源[：:]\s*(.*)$', line)
            if not match:
                continue

            same_line_value = (match.group(1) or "").strip()
            if same_line_value:
                for part in re.split(r'[、;；]', same_line_value):
                    add_source(part)

            follow_index = index + 1
            while follow_index < len(lines):
                candidate = lines[follow_index].strip()
                if not candidate:
                    break
                if re.match(r'^(总结|说明|注[:：]?|附加说明|补充说明)[:：]?', candidate):
                    break
                if re.match(r'^\d+\.\s+\S', candidate) or re.match(r'^[\-*•·●▪◦‣]\s*\S', candidate):
                    add_source(candidate)
                    follow_index += 1
                    continue
                if same_line_value:
                    break
                if re.search(r'(GB|DL|NB|Q/?GDW|CECS|IEC|ISO)', candidate, re.IGNORECASE):
                    add_source(candidate)
                    follow_index += 1
                    continue
                break

        return sources

    @staticmethod
    def _normalize_source_refs(source_refs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        """Normalize source refs, dedupe by file_tag, use full filename as label."""
        normalized: List[Dict[str, str]] = []
        seen_tags: set = set()
        for ref in source_refs or []:
            if not isinstance(ref, dict):
                continue
            file_tag = str(ref.get("file_tag", "")).strip()
            if not file_tag or file_tag in seen_tags:
                continue  # 去重

            # label 就是完整文件名（去掉路径，保留原名）
            label = str(ref.get("label", "")).strip() or file_tag.split("/")[-1].split("\\")[-1]

            normalized.append({
                "file_tag": file_tag,
                "label": label,
                "content_url": str(ref.get("content_url", "")).strip() or ChatService._build_content_url(file_tag),
            })
            seen_tags.add(file_tag)
        return normalized

    @staticmethod
    def _normalize_asset_refs(asset_refs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        seen_tags: set = set()
        for ref in asset_refs or []:
            if not isinstance(ref, dict):
                continue
            asset_tag = str(ref.get("asset_tag", "")).strip()
            if not asset_tag or asset_tag in seen_tags:
                continue
            normalized.append({
                "asset_tag": asset_tag,
                "label": str(ref.get("label", "")).strip() or asset_tag.split("/")[-1],
                "kind": str(ref.get("kind", "")).strip() or "table_image",
                "source_file_tag": str(ref.get("source_file_tag", "")).strip(),
                "content_url": str(ref.get("content_url", "")).strip() or ChatService._build_content_url(asset_tag),
            })
            seen_tags.add(asset_tag)
        return normalized

    @staticmethod
    def _build_content_url(file_tag: str) -> str:
        query = urlencode({"file_tag": file_tag})
        return f"/api/v1/files/content?{query}"

    def _build_sources_block(self, source_refs: List[Dict[str, str]]) -> str:
        """
        构建 sources 区块，注入到正文末尾。
        前端解析此区块后渲染成超链接列表。
        格式：
        <!-- SOURCE_REFS_START -->
        - [文件名](file_tag)
        <!-- SOURCE_REFS_END -->
        """
        if not source_refs:
            return ""

        lines = ["<!-- SOURCE_REFS_START -->"]
        for ref in source_refs:
            file_tag = ref.get("file_tag", "")
            label = ref.get("label", file_tag.split("/")[-1] if file_tag else "")
            if file_tag:
                content_url = self._build_content_url(file_tag)
                lines.append(f"- [{label}]({content_url})")
        lines.append("<!-- SOURCE_REFS_END -->")
        return "\n".join(lines)

    @staticmethod
    def _collect_turn_retrieval_traces() -> List[Dict[str, Any]]:
        """Pull per-turn retrieval traces recorded by DatabaseToolkit."""
        try:
            from app.dependencies import get_database_toolkit

            raw_traces = get_database_toolkit().get_turn_retrieval_traces()
        except Exception as exc:
            logger.warning(f"Failed to collect retrieval traces: {exc}")
            return []

        normalized: List[Dict[str, Any]] = []
        for trace in raw_traces or []:
            if not isinstance(trace, dict):
                continue
            query = str(trace.get("query", "")).strip()
            intent = str(trace.get("intent_description", "")).strip()
            raw_chunks = trace.get("chunks") or []
            chunks: List[Dict[str, Any]] = []
            for chunk in raw_chunks:
                if not isinstance(chunk, dict):
                    continue
                preview = str(chunk.get("preview", "")).strip()
                file_tag = str(chunk.get("file_tag", "")).strip()
                label = str(chunk.get("label", "")).strip() or (
                    file_tag.split("/")[-1].split("\\")[-1] if file_tag else ""
                )
                try:
                    score = float(chunk.get("score", 0.0))
                except Exception:
                    score = 0.0
                if not preview and not file_tag:
                    continue
                chunks.append(
                    {
                        "file_tag": file_tag,
                        "label": label or "未知来源",
                        "score": round(score, 4),
                        "preview": preview,
                    }
                )
            # 允许 chunks 为空（例如无新结果），但只记录有 query 或 intent 的 trace
            if not query and not intent and not chunks:
                continue
            normalized.append(
                {
                    "query": query,
                    "intent_description": intent,
                    "chunks": chunks,
                }
            )
        return normalized

    def _collect_turn_source_refs(self, content: str) -> List[Dict[str, str]]:
        try:
            from app.dependencies import get_database_toolkit

            toolkit_refs = self._normalize_source_refs(
                get_database_toolkit().get_turn_source_refs()
            )
            if toolkit_refs:
                return toolkit_refs
        except Exception as exc:
            logger.warning(f"Failed to collect tool-based source refs: {exc}")

        fallback_refs: List[Dict[str, str]] = []
        seen_tags: set = set()
        for src in self._extract_sources(content):
            file_tag = src.strip()
            if not file_tag or file_tag in seen_tags:
                continue
            fallback_refs.append({
                "file_tag": file_tag,
                "label": file_tag.split("/")[-1],
            })
            seen_tags.add(file_tag)

        if fallback_refs:
            return fallback_refs

        for ref in self._extract_source_refs_from_image_paths(content):
            file_tag = ref["file_tag"]
            if file_tag in seen_tags:
                continue
            fallback_refs.append(ref)
            seen_tags.add(file_tag)
        return fallback_refs

    def _collect_turn_asset_refs(self, content: str, source_refs: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        try:
            from app.dependencies import get_database_toolkit

            toolkit_refs = self._normalize_asset_refs(
                get_database_toolkit().get_turn_asset_refs()
            )
            if toolkit_refs:
                return toolkit_refs
        except Exception as exc:
            logger.warning(f"Failed to collect tool-based asset refs: {exc}")

        image_matches = self._extract_image_asset_refs_from_content(content, source_refs=source_refs)
        return self._normalize_asset_refs(image_matches)

    @staticmethod
    def _extract_source_refs_from_image_paths(content: str) -> List[Dict[str, str]]:
        refs: List[Dict[str, str]] = []
        seen_tags: set = set()

        for match in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', content or ""):
            raw_path = (match.group(1) or "").strip().strip("<>").strip()
            if not raw_path:
                continue

            normalized_path = raw_path.replace("\\", "/")
            if "mineru_output/" not in normalized_path:
                continue

            image_name = normalized_path.rsplit("/", 1)[-1]
            stem = Path(image_name).stem
            stem = re.sub(r"_\d+$", "", stem)
            if not stem:
                continue

            file_tag = f"data/stored_files/{stem}.pdf"
            if file_tag in seen_tags:
                continue

            refs.append({
                "file_tag": file_tag,
                "label": f"{stem}.pdf",
            })
            seen_tags.add(file_tag)

        return refs

    @staticmethod
    def _extract_image_asset_refs_from_content(
        content: str,
        *,
        source_refs: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        refs: List[Dict[str, str]] = []
        seen_tags: set = set()
        fallback_source_tag = ""
        if source_refs:
            fallback_source_tag = str(source_refs[0].get("file_tag", "")).strip()

        for match in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', content or ""):
            raw_path = (match.group(1) or "").strip().strip("<>").strip()
            if not raw_path:
                continue
            normalized_path = raw_path.replace("\\", "/")
            if "mineru_output/" not in normalized_path:
                continue
            asset_tag = normalized_path.lstrip("/")
            if not asset_tag.startswith("data/stored_files/"):
                if asset_tag.startswith("mineru_output/"):
                    asset_tag = f"data/stored_files/{asset_tag}"
                elif "mineru_output/" in asset_tag:
                    asset_tag = f"data/stored_files/mineru_output/{asset_tag.split('mineru_output/', 1)[-1]}"
            if asset_tag in seen_tags:
                continue
            source_file_tag = fallback_source_tag
            if not source_file_tag:
                image_name = asset_tag.rsplit("/", 1)[-1]
                stem = Path(image_name).stem
                stem = re.sub(r"_\d+$", "", stem)
                if stem:
                    source_file_tag = f"data/stored_files/{stem}.pdf"
            refs.append({
                "asset_tag": asset_tag,
                "label": asset_tag.split("/")[-1],
                "kind": "table_image",
                "source_file_tag": source_file_tag,
            })
            seen_tags.add(asset_tag)
        return refs

    @staticmethod
    def _strip_kb_image_markdown(content: str) -> str:
        if not content:
            return content

        cleaned = re.sub(
            r'^[ \t]*!\[[^\]]*\]\((?:[^)\n]*mineru_output/[^)\n]*)\)[ \t]*$',
            '',
            content,
            flags=re.MULTILINE,
        )
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def clear_session(self, username: str, session_id: str) -> bool:
        """Clear a chat session"""
        return self.session_manager.clear_session(username, session_id)

    def list_sessions(self, username: str) -> List[dict]:
        """List persisted chat sessions for the current user."""
        return self.session_manager.list_sessions(username)

    def get_session_detail(self, username: str, session_id: str) -> Optional[dict]:
        """Get persisted session detail for the current user."""
        return self.session_manager.get_session_detail(username, session_id)

    def query_rag_sync(self, query: str) -> Dict[str, Any]:
        """
        Synchronous RAG query for external API access.

        This method performs a one-shot RAG query without session management,
        suitable for API-based integration.

        Args:
            query: User question

        Returns:
            Dict with 'answer' and 'sources' keys
        """
        from app.core.agent_factory import create_chat_agent
        from app.dependencies import get_database_toolkit
        from camel.messages.base import BaseMessage

        logger.info(f"[RAG API] Processing query: {query[:100]}...")

        # Get database toolkit for retrieval tools
        database_toolkit = get_database_toolkit()
        database_toolkit.begin_turn()

        try:
            # Create a fresh agent for this query
            agent = create_chat_agent(database_toolkit=database_toolkit)

            # Perform the query
            full_response = ""
            full_reasoning = ""

            # Use agent.step() which internally calls tools
            response = agent.step(query)

            # Collect response chunks
            for chunk_response in response:
                if hasattr(chunk_response, 'msgs') and len(chunk_response.msgs) > 0:
                    msg = chunk_response.msgs[0]

                    # Collect reasoning
                    reasoning_text = self._extract_reasoning_text(msg)
                    if reasoning_text and not self._is_tool_content(reasoning_text):
                        if reasoning_text.startswith(full_reasoning):
                            full_reasoning = reasoning_text
                        else:
                            full_reasoning += reasoning_text

                    # Collect content
                    content_text = msg.content
                    if content_text and not self._is_tool_content(content_text):
                        if content_text.startswith(full_response):
                            full_response = content_text
                        else:
                            full_response += content_text

            # Get final content if needed
            if not full_response:
                if hasattr(response, 'msg') and hasattr(response.msg, 'content'):
                    full_response = response.msg.content
                elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                    full_response = response.msgs[-1].content
                else:
                    full_response = "抱歉，无法生成回复。"

            raw_full_response = full_response

            # Extract sources from response
            sources = self._collect_turn_source_refs(raw_full_response)
            assets = self._collect_turn_asset_refs(raw_full_response, source_refs=sources)
            if not sources and not assets:
                self._backfill_turn_refs(username="", session_id="sync", message=query)
                sources = self._collect_turn_source_refs(raw_full_response)
                assets = self._collect_turn_asset_refs(raw_full_response, source_refs=sources)

            logger.info(f"[RAG API] Query completed. Sources: {sources}")

            return {
                "answer": full_response,
                "sources": sources,
                "assets": assets,
            }
        except Exception as e:
            logger.exception(f"[RAG API] Query failed: {e}")
            return {
                "answer": f"查询失败: {str(e)}",
                "sources": [],
                "assets": [],
            }
        finally:
            with suppress(Exception):
                database_toolkit.end_turn()
