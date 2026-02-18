"""FastAPI dependency injection functions."""
from fastapi import Request

from neoflow.config import Config
from neoflow.api.session_manager import SessionManager


def get_config(request: Request) -> Config:
    """Get the application config from app state."""
    return request.app.state.config


def get_session_manager(request: Request) -> SessionManager:
    """Get the session manager from app state."""
    return request.app.state.session_manager
