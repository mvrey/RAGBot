from fastapi import APIRouter

from ragbot.core.Embeddings import get_embedder
from ragbot.core.LLM import get_model_name, missing_api_key
from ragbot.api.schemas import ConfigResponse, HealthResponse

router = APIRouter(tags=['meta'])


@router.get('/health', response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status='ok',
        chat_model=get_model_name(),
        embedder=get_embedder().name,
        missing_api_key=missing_api_key(),
    )


@router.get('/config', response_model=ConfigResponse)
def config() -> ConfigResponse:
    return ConfigResponse.build()
