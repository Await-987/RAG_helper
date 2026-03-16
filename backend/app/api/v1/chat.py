"""
Chat API routes with SSE streaming.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse, ClearSessionResponse
from app.services import ChatService
from app.dependencies import get_chat_service, get_current_user

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Stream chat response via Server-Sent Events (SSE).

    The response is a stream of SSE events with the following types:
    - **session**: Contains session_id for conversation continuity
    - **reasoning**: Reasoning content chunks (if model provides them)
    - **content**: Response content chunks
    - **done**: Final event with complete response
    - **error**: Error event if something goes wrong

    - **message**: User message
    - **session_id**: Optional session ID for conversation continuity
    """
    return StreamingResponse(
        chat_service.stream_chat(
            message=request.message,
            username=current_user["username"],
            session_id=request.session_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/session/{session_id}", response_model=ClearSessionResponse)
async def clear_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Clear a chat session and its conversation history.

    - **session_id**: Session ID to clear
    """
    success = chat_service.clear_session(current_user["username"], session_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )

    return ClearSessionResponse(
        success=True,
        message=f"Session '{session_id}' cleared successfully",
        session_id=session_id
    )
