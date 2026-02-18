"""FastAPI application factory and configuration."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from neoflow.config import Config
from neoflow.api.session_manager import SessionManager
from neoflow.api.middleware import logging_middleware, create_error_handler
from neoflow.api.routes import health, query, sessions, templates

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle events."""
    # Startup
    logger.info("Starting NeoFlow API server")
    session_manager: SessionManager = app.state.session_manager
    await session_manager.start_cleanup_task()
    logger.info("Session cleanup task started")

    yield

    # Shutdown
    logger.info("Shutting down NeoFlow API server")
    await session_manager.stop_cleanup_task()
    logger.info("Session cleanup task stopped")


def create_app(config: Config) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        config: Application configuration

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="NeoFlow API",
        description=(
            "REST API for searching and analyzing support tickets "
            "using AI/ML (Weaviate + Ollama). Provides both stateless query "
            "endpoints and stateful session-based chat interactions."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # Store config and session manager in app state
    app.state.config = config
    app.state.session_manager = SessionManager(
        ttl_minutes=config.server.session_ttl_minutes,
        max_sessions=config.server.max_sessions,
        history_dir=config.chat.history_dir,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add logging middleware
    app.middleware("http")(logging_middleware)

    # Add global exception handler
    create_error_handler(app)

    # Register routes
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(sessions.router)
    app.include_router(templates.router)

    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "NeoFlow API",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/api/v1/health",
        }

    logger.info("FastAPI application created")
    return app
