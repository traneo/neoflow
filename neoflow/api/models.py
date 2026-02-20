"""Pydantic models for API request and response validation."""
from datetime import datetime
from pydantic import BaseModel, Field


# Request Models

class QueryRequest(BaseModel):
    """Request model for simple query endpoint."""
    query: str = Field(..., description="The search query", min_length=1)
    project_keyword: str = Field(default="", description="Project name or keyword to filter by")
    include_code: bool = Field(default=False, description="Include code search results")
    include_system_prompt: bool = Field(
        default=True,
        description="Include NeoFlow system prompt when generating the answer",
    )


class SessionCreateRequest(BaseModel):
    """Request model for creating a new session."""
    include_code: bool = Field(default=False, description="Include code search in this session")
    save_history: bool = Field(default=True, description="Save conversation history on session end")


class SessionQueryRequest(BaseModel):
    """Request model for querying within a session."""
    query: str = Field(..., description="The search query", min_length=1)
    project_keyword: str = Field(default="", description="Project name or keyword to filter by")


class TemplateQueryRequest(BaseModel):
    """Request model for template-based queries."""
    template_name: str = Field(..., description="Name of the template to use")
    template_values: dict[str, str] = Field(default_factory=dict, description="Values for template fields")


# Response Models

class QueryResponse(BaseModel):
    """Response model for query results."""
    answer: str = Field(..., description="The generated answer in markdown format")
    query: str = Field(..., description="The original query")
    project_keyword: str = Field(..., description="The project keyword used")
    include_code: bool = Field(..., description="Whether code search was included")
    timestamp: str = Field(..., description="ISO format timestamp of the query")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")


class SessionResponse(BaseModel):
    """Response model for session metadata."""
    session_id: str = Field(..., description="Unique session identifier")
    created_at: str = Field(..., description="ISO format timestamp of session creation")
    last_activity: str = Field(..., description="ISO format timestamp of last activity")
    include_code: bool = Field(..., description="Whether code search is enabled for this session")
    save_history: bool = Field(..., description="Whether history will be saved on session end")
    query_count: int = Field(..., description="Number of queries executed in this session")


class HistoryEntry(BaseModel):
    """Single entry in conversation history."""
    timestamp: str = Field(..., description="ISO format timestamp")
    keyword: str = Field(..., description="Project keyword used")
    query: str = Field(..., description="The query text")
    code_search: bool = Field(..., description="Whether code search was used")
    answer: str = Field(..., description="The generated answer")


class SessionHistoryResponse(BaseModel):
    """Response model for session history."""
    session_id: str = Field(..., description="Session identifier")
    history: list[HistoryEntry] = Field(..., description="List of conversation entries")


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Overall status: 'healthy' or 'degraded'")
    weaviate: bool = Field(..., description="Weaviate connection status")
    ollama: bool = Field(..., description="Ollama connection status")


class TemplateInfo(BaseModel):
    """Information about a query template."""
    name: str = Field(..., description="Template identifier")
    title: str = Field(..., description="Human-readable template title")
    fields: list[str] = Field(..., description="List of field names required by template")


class TemplatesResponse(BaseModel):
    """Response model for template listing."""
    templates: list[TemplateInfo] = Field(..., description="Available query templates")


class ErrorResponse(BaseModel):
    """Response model for errors."""
    error: str = Field(..., description="Error type or title")
    detail: str = Field(..., description="Detailed error message")


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str = Field(..., description="Status or informational message")
