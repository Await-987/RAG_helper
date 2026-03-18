"""
Chat service with session management.
"""
import sys
import uuid
import json
import re
from pathlib import Path
from contextlib import suppress
from datetime import datetime
from typing import Dict, Optional, Generator, Any, Tuple, List
from loguru import logger
from pydantic import BaseModel, Field

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
            from app.core.model_runtime import build_token_counter
            from camel.memories import (
                ChatHistoryBlock,
                LongtermAgentMemory,
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

            memory = LongtermAgentMemory(
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

    def _restore_session_memory(self, username: str, session_id: str, chat_agent: ChatAgent) -> None:
        """Restore persisted memory for an existing session ID if available."""
        memory_path = self._get_memory_path(username, session_id)
        if not memory_path.exists():
            return

        if not hasattr(chat_agent, "load_memory_from_path"):
            logger.warning("ChatAgent does not support load_memory_from_path, skip memory restore")
            return

        try:
            chat_agent.load_memory_from_path(str(memory_path))
            logger.info(f"Restored agent memory from {memory_path}")
        except Exception as exc:
            logger.warning(f"Failed to restore agent memory from {memory_path}: {exc}")

    def save_session_memory(self, username: str, session_id: str) -> None:
        """Persist a session memory snapshot to disk."""
        chat_agent = self._sessions.get(session_id)
        if chat_agent is None:
            return

        if not hasattr(chat_agent, "save_memory"):
            logger.warning("ChatAgent does not support save_memory, skip persistence")
            return

        memory_path = self._get_memory_path(username, session_id)
        try:
            chat_agent.save_memory(str(memory_path))
            logger.debug(f"Saved agent memory to {memory_path}")
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
                system_message=BaseMessage.make_assistant_message(
                    role_name="Intent Router",
                    content=(
                        "你是一个对话路由器。你的任务是判断当前用户问题在本轮回答前是否必须强制检索知识库。"
                        "如果问题需要基于文档、标准、流程、定义、参数、条件、范围、职责、原因、区别、是否、多少等事实性内容回答，"
                        "则 needs_search=true。"
                        "如果只是寒暄、闲聊、改写、润色、总结用户刚刚提供的文本、表达偏好、纯主观建议，"
                        "则 needs_search=false。"
                        "必须结合最近对话上下文理解代词和追问。"
                    ),
                ),
                model=backend_model(),
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
                system_message=BaseMessage.make_assistant_message(
                    role_name="Search Rewriter",
                    content=(
                        "你是一个知识库检索改写器。你的任务是结合最近对话上下文，"
                        "把当前用户追问改写成适合检索的 query 和 intent_description。"
                        "你必须解决代词、简称、追问、省略主语等问题，把被省略的主体补全。"
                        "如果当前问题明显是在追问上一轮某个标准、文件、设备、流程、制度、表格、章节，"
                        "必须把该主体完整补回 query 和 intent_description。"
                        "expanded_queries 最多给 2 条，只能用于补充别名、简称、表号、同义表达或缺失维度；"
                        "严禁给出无关扩展，严禁泛化到别的文档。"
                        "如果用户明确在问'涉及的表/附表/表格/图片/图表/明细表'，"
                        "expanded_queries 应优先补充表号、清单表、投标报价表、附表等检索词。"
                    ),
                ),
                model=backend_model(),
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
            "最近对话上下文：\n"
            + ("\n".join(context_lines) if context_lines else "无")
            + f"\n\n当前用户问题：{message}\n\n"
            "请输出结构化检索改写结果：\n"
            "1. query: 3-12 个核心检索词，必须补全被省略主体；\n"
            "2. intent_description: 完整自然语言检索意图；\n"
            "3. expanded_queries: 最多 2 条，仅用于别名/简称/表号/补充维度；\n"
            "4. referent: 当前追问真正指向的主体；\n"
            "5. reason: 简短说明。\n"
            "如果当前消息本身已经完整明确，也要保持 query 足够具体，禁止只返回笼统词语。"
        )

        try:
            planner = self._get_search_rewriter()
            response = planner.step(planner_prompt, response_format=SearchRewritePlan)
            parsed = None
            if hasattr(response, "msgs") and response.msgs:
                parsed = getattr(response.msgs[-1], "parsed", None)
            if parsed is None:
                raise ValueError("search rewriter returned no structured result")

            if isinstance(parsed, SearchRewritePlan):
                plan = parsed
            elif hasattr(SearchRewritePlan, "model_validate"):
                plan = SearchRewritePlan.model_validate(parsed)
            else:
                plan = SearchRewritePlan.parse_obj(parsed)
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
            referent = ""
            for item in reversed(recent_messages[:-1]):
                if item.get("role") != "user":
                    continue
                prior = str(item.get("content") or "").replace("\n", " ").strip()
                if not prior:
                    continue
                referent = prior[:80]
                break
            if referent and any(token in message for token in ("它", "这个", "这个规范", "该规范", "该标准", "涉及", "这些", "那些", "相关")):
                query = self._keywordize_query(f"{referent} {message}")
                intent_description = f"{referent}。当前追问：{message}"
            else:
                query = self._keywordize_query(message)
                intent_description = message
            return SearchRewritePlan(
                query=query,
                intent_description=intent_description,
                expanded_queries=[],
                referent=referent,
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

    def _build_factual_prompt_with_evidence(self, message: str, evidence: str) -> str:
        return (
            "这是事实性问题。后端已经强制检索了知识库，你必须仅基于下面提供的检索结果回答。"
            "如果证据不足，只能明确说知识库中未找到或证据不足；禁止脱离检索结果补充常识。\n\n"
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
            return self._truncate_for_prompt(merged_evidence, settings.FACTUAL_EVIDENCE_MAX_CHARS)
        except Exception as exc:
            logger.warning(f"Forced factual search failed: {exc}")
            return (
                "知识库检索在本轮执行失败。你必须明确说明检索失败或证据不足，"
                "不要基于历史记忆或常识自行作答。"
            )

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
            yield self._format_sse("session", {"session_id": session_id})

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
                            if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                                reasoning_text = msg.reasoning_content

                                # Filter tool-related content
                                if not self._is_tool_content(reasoning_text):
                                    if reasoning_text.startswith(full_reasoning):
                                        full_reasoning = reasoning_text
                                    else:
                                        full_reasoning += reasoning_text

                                    yield self._format_sse("reasoning", {
                                        "content": reasoning_text,
                                    })

                            # Handle response content
                            content_text = msg.content
                            if content_text and not self._is_tool_content(content_text):
                                if content_text.startswith(full_response):
                                    full_response = content_text
                                else:
                                    full_response += content_text

                                yield self._format_sse("content", {
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

            # Send done event
            response_blocks = [block.model_dump() for block in _build_content_blocks(full_response)]
            reasoning_blocks = [block.model_dump() for block in _build_content_blocks(full_reasoning)] if full_reasoning else None
            self.session_manager.append_transcript_message(
                username,
                session_id,
                role="assistant",
                content=full_response,
                blocks=response_blocks,
                reasoning=full_reasoning or None,
                reasoning_blocks=reasoning_blocks,
            )
            self.session_manager.save_session_memory(username, session_id)

            yield self._format_sse("done", {
                "reasoning": full_reasoning,
                "reasoning_blocks": reasoning_blocks,
                "content": full_response,
                "blocks": response_blocks,
                "session_id": session_id
            })

        except Exception as e:
            if self._is_token_limit_error(e):
                logger.warning(f"Top-level token limit fallback for session {session_id if 'session_id' in locals() else 'unknown'}")
                yield self._format_sse("done", {
                    "reasoning": "",
                    "reasoning_blocks": None,
                    "content": self._build_new_chat_required_message(),
                    "blocks": [block.model_dump() for block in _build_content_blocks(self._build_new_chat_required_message())],
                    "session_id": session_id if 'session_id' in locals() else None,
                })
                return
            logger.exception(f"Chat streaming error: {e}")
            yield self._format_sse("error", {"message": str(e)})
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

    def _format_sse(self, event_type: str, data: dict) -> str:
        """Format data as SSE event"""
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def clear_session(self, username: str, session_id: str) -> bool:
        """Clear a chat session"""
        return self.session_manager.clear_session(username, session_id)

    def list_sessions(self, username: str) -> List[dict]:
        """List persisted chat sessions for the current user."""
        return self.session_manager.list_sessions(username)

    def get_session_detail(self, username: str, session_id: str) -> Optional[dict]:
        """Get persisted session detail for the current user."""
        return self.session_manager.get_session_detail(username, session_id)
