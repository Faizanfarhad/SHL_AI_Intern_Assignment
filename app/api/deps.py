from functools import lru_cache

from app.core.config import get_settings
from app.services.catalog_service import CatalogService
from app.services.chat_service import ChatService
from app.services.langchain_agent import LangChainAgentRunner


@lru_cache
def get_catalog_service() -> CatalogService:
    settings = get_settings()
    return CatalogService(settings.catalog_path)


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        catalog_service=get_catalog_service(),
        agent_runner=LangChainAgentRunner.create(
            catalog_service=get_catalog_service(),
            model_name=settings.shl_agent_model,
            base_url=settings.shl_agent_base_url,
        ),
        max_recommendations=settings.max_recommendations,
        min_context_signals=settings.min_context_signals,
    )
