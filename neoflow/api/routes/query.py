"""Simple query endpoints (stateless)."""
import logging
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from rich.console import Console

from neoflow.config import Config
from neoflow.api.dependencies import get_config
from neoflow.api.models import QueryRequest, QueryResponse
from neoflow.chat import run_chat
from neoflow.status_bar import StatusBar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    config: Config = Depends(get_config),
):
    """
    Execute a single stateless query.

    This endpoint performs a one-off search without maintaining session history.
    Use this for simple queries where conversation context is not needed.

    **Parameters:**
    - **query**: The search query text
    - **project_keyword**: Optional project name or keyword to filter results
    - **include_code**: Whether to include GitLab code search results

    **Returns:**
    - The generated answer in markdown format
    - Query metadata and execution time
    """
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

        return QueryResponse(
            answer=answer,
            query=request.query,
            project_keyword=request.project_keyword,
            include_code=request.include_code,
            timestamp=datetime.now().isoformat(),
            execution_time_ms=execution_time_ms,
        )
    except Exception as e:
        logger.error("Query execution failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )
