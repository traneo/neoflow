from fastapi import APIRouter
from neoflow.api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check the health of the system services."""
    # This is a placeholder implementation
    # In a real implementation, this would check Weaviate and Ollama connectivity
    return HealthResponse(
        status="healthy",
        weaviate=True,
        ollama=True,
    )
