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

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from camel.agents.chat_agent import ChatAgent
from camel.messages.base import BaseMessage

from app.config import settings
from app.schemas.chat import ChatMessage


class SessionManager:
    """
    Manages ChatAgent sessions for different users.
    Each session maintains its own conversation history.
    """

    def __init__(self):
        self._sessions: Dict[str, ChatAgent] = {}
        self._session_metadata: Dict[str, dict] = {}
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

    def _load_session_transcript(self, username: str, session_id: str) -> Optional[dict]:
        session_path = self._get_session_path(username, session_id)
        if not session_path.exists():
            return None
        try:
            return json.loads(session_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load session transcript from {session_path}: {exc}")
            return None

    def _save_session_transcript(self, username: str, session_id: str, transcript: dict) -> None:
        session_path = self._get_session_path(username, session_id)
        session_path.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2),
            encoding="utf-8",
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
        reasoning: Optional[str] = None,
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
                "reasoning": reasoning,
                "timestamp": datetime.now().isoformat(),
            }
        )
        transcript["updated_at"] = datetime.now().isoformat()
        self._save_session_transcript(username, session_id, transcript)

    def list_sessions(self, username: str) -> List[dict]:
        user_dir = self._get_user_session_dir(username)
        sessions: List[dict] = []

        for session_file in user_dir.glob("*.json"):
            try:
                transcript = json.loads(session_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Failed to parse session transcript {session_file}: {exc}")
                continue

            messages = transcript.get("messages", [])
            created_at = transcript.get("created_at") or datetime.now().isoformat()
            updated_at = transcript.get("updated_at") or created_at
            sessions.append(
                {
                    "session_id": transcript.get("session_id", session_file.stem),
                    "title": transcript.get("title") or "新对话",
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "message_count": len(messages),
                    "last_activity": updated_at,
                    "username": username,
                }
            )

        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        return sessions

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
            from agents.backend_model import _build_token_counter
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
                token_counter=_build_token_counter(),
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

        existing_metadata = self._session_metadata.get(session_id)
        if existing_metadata and existing_metadata.get("username") != username:
            raise PermissionError(f"Session '{session_id}' does not belong to user '{username}'")

        if session_id not in self._sessions:
            logger.info(f"Creating new chat session: {session_id}")
            self._sessions[session_id] = self._create_chat_agent()
            self._restore_session_memory(username, session_id, self._sessions[session_id])
            self._session_metadata[session_id] = {
                "username": username,
                "created_at": datetime.now(),
                "message_count": 0,
                "last_activity": datetime.now(),
                "memory_enabled": bool(getattr(self._sessions[session_id], "memory", None)),
            }

        # Update last activity
        self._session_metadata[session_id]["last_activity"] = datetime.now()

        return session_id, self._sessions[session_id]

    def _create_chat_agent(self) -> ChatAgent:
        """Create a new ChatAgent instance"""
        # Import here to avoid circular dependency
        from app.dependencies import get_database_toolkit

        system_message = r'''
        你是电力系统与国家电网业务场景的知识问答智能体。
        只允许基于知识库内容回答，知识库是唯一事实来源。

        回答规则：
        1. 每一轮事实性问题都必须调用 `search_database`，严禁跳过检索直接基于历史回答。
        2. 多轮对话中的历史信息只允许用于理解指代、补全主体、改写 query 和 intent_description；历史回答、历史检索结果、历史摘要都不能直接当作本轮证据。
        3. 即使上一轮刚检索过，只要本轮用户继续追问事实、参数、条件、范围、原因、差异、是否、能否、多少、哪一条、哪一项等内容，也必须重新调用 `search_database`。
        4. 严禁基于历史检索结果直接做肯定回答或否定回答，必须以本轮新检索得到的内容为准。
        5. 工具返回的是已筛选的高相关完整原文 chunk，优先基于这些原文作答；证据不足时再补充一次检索，不要一次索取大量证据。
        6. 不得编造标准条文、技术参数、职责分工、流程结论。只有在本轮调用工具后仍然没有获得相关信息时，才可以回答“当前知识库中未找到相关信息”或“现有资料不足以确认结论”。
        7. 回答必须标注来源；多来源时明确说明来自多个文件。
        8. 可以整理、压缩、结构化原文，但不得引入知识库中不存在的新事实。
        9. 回答保持客观、克制、专业，避免“通常来说”“一般认为”“业内普遍”等无来源表述。
        10. 只有当链接对应的是表格证据时，才允许输出图片链接，例如 `![表格](mineru_output/xxx.jpg)`；非表格图片链接默认不要输出。
        11. 如果需要输出表格图片链接，必须逐字符原样保留，严禁改写图片路径或文件名中的任何字符；不得补全、简写、纠正、翻译、清洗标题，也不得自作主张替换括号内文字。工具返回什么路径，就必须输出什么路径。
        12. 如果同一证据同时有表格文本和表格图片链接，允许同时保留两者，但图片链接仍必须原样输出。
        13. 公式使用 LaTeX；表格使用 Markdown；复杂表格优先保留原图链接；非表格图片不要主动输出。

        调用 `search_database` 时，必须同时传入以下两个参数，严禁缺漏：

        * 参数 1: `query` (用于召回)
          - 动作：将用户提问精炼为 3-8 个核心关键词。
          - 约束：必须保留原说法中的所有数字、单位、百分比、范围等数值信息；保留标准编号、专业术语。
          - 约束：优先少量高相关证据，避免无关证据堆积。
          - 约束：若当前提问包含代词（如“它”、“这个”、“其”、“该标准”等）或属于对前文的追问，必须结合上下文语义，将被省略的主体对象补全到检索 query 中。
          - 禁止：严禁将用户原句整体原样传给工具。

        * 参数 2: `intent_description` (用于重排)
          - 动作：基于对话历史，改写为一个完整的自然语言问句，最接近用户的真实意图。
          - 原则：消除所有模糊代词，将“它”、“该标准”等还原为具体名称，补全被省略的背景主体。
          - 约束：必须是一个完整句子或疑问句，而不是关键词列表。
          - 目标：用最接近用户真实意图的完整表述，精确匹配语义最相关的文本模块。

        改写示例：
        * 用户第一轮：“500kV变压器的绝缘等级是多少？”
        * query: "500kV 变压器 绝缘等级"
        * intent_description: "500kV变压器的绝缘等级是多少？"
        * 用户第二轮（追问）：“那它的能效呢？”
        * query: "500kV 变压器 能效"
        * intent_description: "500kV变压器的能效要求是多少？"

        总目标：
        只输出能被知识库原文直接支撑、且来源清晰可追溯的答案。
        '''

        # Use cached DatabaseToolkit
        database_toolkit = get_database_toolkit()

        # Create stream model
        from agents import stream_model

        agent_memory = self._build_agent_memory()

        return ChatAgent(
            system_message=BaseMessage.make_assistant_message(
                role_name="Chat Agent",
                content=system_message,
            ),
            model=stream_model(),
            memory=agent_memory,
            tools=[*database_toolkit.get_tools()],
            message_window_size=12,
            summarize_threshold=20,
            prune_tool_calls_from_memory=True,
            stream_accumulate=False
        )

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
        metadata = self._session_metadata.get(session_id)
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
            if session_id in self._session_metadata:
                del self._session_metadata[session_id]
            with suppress(FileNotFoundError):
                self._get_memory_path(username, session_id).unlink()
            with suppress(FileNotFoundError):
                self._get_session_path(username, session_id).unlink()
            logger.info(f"Session cleared: {session_id}")
            return True

        if transcript is not None:
            with suppress(FileNotFoundError):
                self._get_memory_path(username, session_id).unlink()
            with suppress(FileNotFoundError):
                self._get_session_path(username, session_id).unlink()
            logger.info(f"Persisted session cleared: {session_id}")
            return True
        return False

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """Get session metadata"""
        return self._session_metadata.get(session_id)

    def increment_message_count(self, session_id: str):
        """Increment message count for a session"""
        if session_id in self._session_metadata:
            self._session_metadata[session_id]["message_count"] += 1
            self._session_metadata[session_id]["last_activity"] = datetime.now()


class ChatService:
    """Chat service handling streaming responses"""

    def __init__(self):
        self.session_manager = SessionManager()

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

            self.session_manager.append_transcript_message(
                username,
                session_id,
                role="user",
                content=message,
            )

            # Increment message count
            self.session_manager.increment_message_count(session_id)

            self._log_context_budget(chat_agent, message)

            # Send session ID first
            yield self._format_sse("session", {"session_id": session_id})

            # Stream response
            full_reasoning = ""
            full_response = ""

            response = chat_agent.step(message)

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

                            # Send reasoning chunk
                            yield self._format_sse("reasoning", {
                                "content": reasoning_text,
                                "full": full_reasoning
                            })

                    # Handle response content
                    content_text = msg.content
                    if content_text and not self._is_tool_content(content_text):
                        if content_text.startswith(full_response):
                            full_response = content_text
                        else:
                            full_response += content_text

                        # Send content chunk
                        yield self._format_sse("content", {
                            "content": content_text,
                            "full": full_response
                        })

            # Get final content if needed
            if not full_response:
                if hasattr(response, 'msg') and hasattr(response.msg, 'content'):
                    full_response = response.msg.content
                elif hasattr(response, 'msgs') and len(response.msgs) > 0:
                    full_response = response.msgs[-1].content
                else:
                    full_response = "抱歉，我无法生成回复。"

            # Send done event
            self.session_manager.append_transcript_message(
                username,
                session_id,
                role="assistant",
                content=full_response,
                reasoning=full_reasoning or None,
            )
            self.session_manager.save_session_memory(username, session_id)

            yield self._format_sse("done", {
                "reasoning": full_reasoning,
                "content": full_response,
                "session_id": session_id
            })

        except Exception as e:
            logger.exception(f"Chat streaming error: {e}")
            yield self._format_sse("error", {"message": str(e)})

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
