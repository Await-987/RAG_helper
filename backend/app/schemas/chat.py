"""
Chat schemas.
"""
from datetime import datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request schema"""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class ChatContentBlock(BaseModel):
    """Structured chat content block."""

    type: Literal["markdown", "math", "table", "code"] = Field(..., description="Block type")
    content: str = Field(..., description="Block content")


class ChatMessage(BaseModel):
    """Chat message schema"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    blocks: Optional[List[ChatContentBlock]] = Field(None, description="Structured content blocks")
    reasoning: Optional[str] = Field(None, description="Reasoning content (for assistant messages)")
    reasoning_blocks: Optional[List[ChatContentBlock]] = Field(None, description="Structured reasoning blocks")
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatStreamChunk(BaseModel):
    """Chat stream chunk schema for SSE"""
    type: str = Field(..., description="Chunk type: 'content', 'reasoning', 'done', 'error'")
    content: Optional[str] = None
    blocks: Optional[List[ChatContentBlock]] = None
    reasoning: Optional[str] = None
    reasoning_blocks: Optional[List[ChatContentBlock]] = None
    done: bool = False
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """Complete chat response schema"""
    message: ChatMessage
    session_id: str


class SessionInfo(BaseModel):
    """Session information schema"""
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_activity: datetime
    username: Optional[str] = None


class SessionListResponse(BaseModel):
    """Session list response schema"""
    sessions: List[SessionInfo]


class SessionDetailResponse(BaseModel):
    """Session detail response schema"""
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessage]


class ClearSessionResponse(BaseModel):
    """Clear session response schema"""
    success: bool
    message: str
    session_id: str
