from __future__ import annotations

import json
import os
from typing import Any, Callable

from app.prompts.shl_agent_prompt import SYSTEM_PROMPT
from app.services.catalog_service import CatalogItem, CatalogService

create_agent = None
tool: Callable[[Callable[..., Any]], Callable[..., Any]] | None = None
ChatOpenAI = None


def _load_langchain() -> tuple[Any, Callable[[Callable[..., Any]], Callable[..., Any]], Any]:
    global create_agent, tool, ChatOpenAI

    if create_agent is not None and tool is not None and ChatOpenAI is not None:
        return create_agent, tool, ChatOpenAI

    try:
        from langchain.agents import create_agent as lc_create_agent
        from langchain.tools import tool as lc_tool
        from langchain_openai import ChatOpenAI as lc_chat_open_ai
    except ImportError as exc:  # pragma: no cover - keeps the scaffold importable before dependencies are installed
        raise RuntimeError("LangChain dependencies are not installed.") from exc

    create_agent = lc_create_agent
    tool = lc_tool
    ChatOpenAI = lc_chat_open_ai
    return create_agent, tool, ChatOpenAI


class LangChainAgentRunner:
    def __init__(self, catalog_service: CatalogService, model_name: str, base_url: str = "") -> None:
        create_agent_fn, _, _ = _load_langchain()

        self.catalog_service = catalog_service
        model = self._build_model(model_name=model_name, base_url=base_url)
        self.agent = create_agent_fn(
            model=model,
            tools=[
                self._build_search_tool(),
                self._build_detail_tool(),
            ],
            system_prompt=SYSTEM_PROMPT,
        )

    @classmethod
    def create(
        cls,
        catalog_service: CatalogService,
        model_name: str,
        base_url: str = "",
    ) -> LangChainAgentRunner | None:
        if not model_name:
            return None

        try:
            return cls(
                catalog_service=catalog_service,
                model_name=model_name,
                base_url=base_url,
            )
        except Exception:
            return None

    def generate_reply(self, messages: list[dict[str, Any]]) -> str | None:
        try:
            result = self.agent.invoke({"messages": messages})
        except Exception:
            return None

        last_message = result["messages"][-1]
        content = getattr(last_message, "content", "")

        if isinstance(content, str):
            return content.strip() or None

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            joined = " ".join(part.strip() for part in text_parts if part.strip())
            return joined or None

        return None

    def _build_search_tool(self):
        catalog_service = self.catalog_service
        _, tool_decorator, _ = _load_langchain()

        @tool_decorator
        def search_shl_catalog(query: str) -> str:
            """Search the SHL catalog for matching assessments and return grounded results."""
            items = catalog_service.search(query, limit=10)
            return json.dumps([self._item_to_payload(item) for item in items], indent=2)

        return search_shl_catalog

    def _build_detail_tool(self):
        catalog_service = self.catalog_service
        _, tool_decorator, _ = _load_langchain()

        @tool_decorator
        def get_assessment_details(name: str) -> str:
            """Fetch one SHL assessment by name for grounded comparison or explanation."""
            matches = catalog_service.find_named_items(name)
            if not matches:
                return json.dumps({"error": f"No assessment found for '{name}'."})
            return json.dumps(self._item_to_payload(matches[0]), indent=2)

        return get_assessment_details

    def _item_to_payload(self, item: CatalogItem) -> dict[str, Any]:
        return {
            "name": item.name,
            "url": item.url,
            "test_type": item.test_type,
            "description": item.description,
            "categories": item.categories,
            "skills": item.skills,
            "job_levels": item.job_levels,
        }

    def _build_model(self, model_name: str, base_url: str):
        _, _, chat_open_ai_cls = _load_langchain()
        provider, resolved_model = self._split_model_name(model_name)

        if provider == "deepseek":
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is not set.")
            return chat_open_ai_cls(
                model=resolved_model,
                api_key=api_key,
                base_url=base_url or "https://api.deepseek.com",
                temperature=0,
            )

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return chat_open_ai_cls(
            model=resolved_model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=0,
        )

    def _split_model_name(self, model_name: str) -> tuple[str, str]:
        if ":" in model_name:
            provider, resolved_model = model_name.split(":", 1)
            return provider.strip().lower(), resolved_model.strip()
        return "openai", model_name.strip()
