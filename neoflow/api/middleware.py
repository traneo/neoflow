"""Middleware and error handlers for the FastAPI application."""
import logging
import time
from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def logging_middleware(request: Request, call_next):
    """Log all requests with timing information."""
    start_time = time.time()

    # Log request
    logger.info("%s %s", request.method, request.url.path)

    # Process request
    response = await call_next(request)

    # Log response with timing
    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        "%s %s - %d (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response


def create_error_handler(app):
    """Add global exception handler to the app."""

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all uncaught exceptions."""
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "detail": str(exc),
            },
        )
