"""FastAPI dependency injection functions."""
from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader

from neoflow.config import Config
from neoflow.api.session_manager import SessionManager

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_config(request: Request) -> Config:
    """Get the application config from app state."""
    return request.app.state.config


def get_session_manager(request: Request) -> SessionManager:
    """Get the session manager from app state."""
    return request.app.state.session_manager


async def verify_api_key(
    request: Request,
    api_key: str | None = None,
) -> None:
    """Verify the API key if one is configured."""
    config: Config = request.app.state.config
    if not config.server.api_key:
        return  # Auth disabled when no key configured
    provided_key = request.headers.get("X-API-Key")
    if provided_key != config.server.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
