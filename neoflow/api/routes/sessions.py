"""Session management endpoints (stateful)."""
import logging
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status

from neoflow.config import Config
from neoflow.api.dependencies import get_config, get_session_manager
from neoflow.api.session_manager import SessionManager
from neoflow.api.models import (
    SessionCreateRequest,
    SessionQueryRequest,
    SessionResponse,
    SessionHistoryResponse,
    QueryResponse,
    MessageResponse,
    HistoryEntry,
)
from rich.console import Console
from neoflow.chat import run_chat
from neoflow.status_bar import StatusBar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SessionCreateRequest,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Create a new chat session.

    Sessions maintain conversation history and allow for multi-turn interactions.
    Each session has a unique ID and can be configured with different settings.

    **Parameters:**
    - **include_code**: Enable code search for all queries in this session
    - **save_history**: Save conversation history to disk when session ends

    **Returns:**
    - Session metadata including unique session_id
    """
    session = await session_manager.create_session(
        include_code=request.include_code,
        save_history=request.save_history,
    )

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
        include_code=session.include_code,
        save_history=session.save_history,
        query_count=session.query_count,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Get session metadata.

    Retrieve information about an existing session including creation time,
    last activity, settings, and query count.

    **Returns:**
    - Session metadata
    - 404 if session not found
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return SessionResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
        include_code=session.include_code,
        save_history=session.save_history,
        query_count=session.query_count,
    )


@router.post("/{session_id}/query", response_model=QueryResponse)
async def session_query(
    session_id: str,
    request: SessionQueryRequest,
    config: Config = Depends(get_config),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Execute a query within a session.

    Performs a search and adds the query and response to the session history.
    The session's include_code setting determines whether code search is performed.

    **Parameters:**
    - **query**: The search query text
    - **project_keyword**: Optional project name or keyword to filter results

    **Returns:**
    - The generated answer with metadata
    - 404 if session not found
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty",
        )

    try:
        start_time = time.time()

        # Create console and statusbar for chat, using silent=True for API
        console = Console()
        bar = StatusBar()
        bar.start()
        
        try:
            # Combine project_keyword and query for chat-based approach
            query_text = request.query
            if request.project_keyword:
                query_text = f"[project: {request.project_keyword}] {request.query}"
            
            # Execute query using chat-based approach
            answer = run_chat(
                query=query_text,
                config=config,
                console=console,
                bar=bar,
                silent=True,
            )
            answer = answer or "No answer generated"
        finally:
            bar.stop()

        execution_time_ms = (time.time() - start_time) * 1000

        # Update session
        session.last_query = request.query
        session.last_keyword = request.project_keyword
        session.last_answer = answer
        session.history.append({
            "timestamp": datetime.now().isoformat(),
            "keyword": request.project_keyword,
            "query": request.query,
            "code_search": session.include_code,
            "answer": answer,
        })

        await session_manager.touch_session(session_id)

        return QueryResponse(
            answer=answer,
            query=request.query,
            project_keyword=request.project_keyword,
            include_code=session.include_code,
            timestamp=datetime.now().isoformat(),
            execution_time_ms=execution_time_ms,
        )
    except Exception as e:
        logger.error("Session query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )


@router.post("/{session_id}/retry", response_model=QueryResponse)
async def retry_query(
    session_id: str,
    config: Config = Depends(get_config),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Retry the last query in a session.

    Re-executes the most recent query using the same parameters.
    Useful for getting fresh results or when a query failed.

    **Returns:**
    - The new answer with updated metadata
    - 404 if session not found
    - 400 if no previous query exists
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if not session.last_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No previous query to retry",
        )

    try:
        start_time = time.time()

        # Create console and statusbar for chat, using silent=True for API
        console = Console()
        bar = StatusBar()
        bar.start()
        
        try:
            # Combine project_keyword and query for chat-based approach
            query_text = session.last_query
            if session.last_keyword:
                query_text = f"[project: {session.last_keyword}] {session.last_query}"
            
            answer = run_chat(
                query=query_text,
                config=config,
                console=console,
                bar=bar,
                silent=True,
            )
            answer = answer or "No answer generated"
        finally:
            bar.stop()

        execution_time_ms = (time.time() - start_time) * 1000

        # Update session with retry
        session.last_answer = answer
        session.history.append({
            "timestamp": datetime.now().isoformat(),
            "keyword": session.last_keyword,
            "query": f"[RETRY] {session.last_query}",
            "code_search": session.include_code,
            "answer": answer,
        })

        await session_manager.touch_session(session_id)

        return QueryResponse(
            answer=answer,
            query=session.last_query,
            project_keyword=session.last_keyword,
            include_code=session.include_code,
            timestamp=datetime.now().isoformat(),
            execution_time_ms=execution_time_ms,
        )
    except Exception as e:
        logger.error("Retry query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )


@router.delete("/{session_id}", response_model=MessageResponse)
async def delete_session(
    session_id: str,
    save: bool = True,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Delete a session.

    Removes the session from memory and optionally saves the conversation
    history to disk if the session was configured with save_history=True.

    **Query Parameters:**
    - **save**: Whether to save history (default: true)

    **Returns:**
    - Success message
    - 404 if session not found
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    await session_manager.delete_session(session_id, save=save)

    return MessageResponse(
        message=f"Session {session_id} deleted successfully",
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_history(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
):
    """
    Get full conversation history for a session.

    Returns all queries and responses in chronological order.

    **Returns:**
    - List of history entries with timestamps
    - 404 if session not found
    """
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    history_entries = [
        HistoryEntry(
            timestamp=entry["timestamp"],
            keyword=entry["keyword"],
            query=entry["query"],
            code_search=entry["code_search"],
            answer=entry["answer"],
        )
        for entry in session.history
    ]

    return SessionHistoryResponse(
        session_id=session_id,
        history=history_entries,
    )
