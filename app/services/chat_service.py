from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.chat import ChatRequest, ChatResponse, Recommendation
from app.services.catalog_service import CatalogItem, CatalogService
from app.services.guardrails import run_guardrails
from app.services.langchain_agent import LangChainAgentRunner
from app.utils.text import normalize_text, tokenize


GENERIC_TOKENS = {
    "a",
    "an",
    "and",
    "assessment",
    "assessments",
    "candidate",
    "for",
    "hire",
    "hiring",
    "i",
    "job",
    "need",
    "role",
    "someone",
    "test",
    "tests",
    "the",
    "to",
    "we",
}

SENIORITY_HINTS = {"entry", "junior", "mid", "senior", "lead", "manager", "director"}
COMPARE_HINTS = {"compare", "comparison", "difference", "different", "versus", "vs"}


@dataclass(frozen=True)
class ConversationContext:
    user_text: str
    latest_user_message: str
    informative_tokens: set[str]
    has_seniority: bool


class ChatService:
    def __init__(
        self,
        catalog_service: CatalogService,
        agent_runner: LangChainAgentRunner | None = None,
        max_recommendations: int = 5,
        min_context_signals: int = 2,
    ) -> None:
        self.catalog_service = catalog_service
        self.agent_runner = agent_runner
        self.max_recommendations = max_recommendations
        self.min_context_signals = min_context_signals

    def reply(self, payload: ChatRequest) -> ChatResponse:
        context = self._build_context(payload)

        if not context.latest_user_message:
            return self._response(
                reply="Tell me what role you are hiring for and what you want to measure.",
                recommendations=[],
                end_of_conversation=False,
            )

        guardrail = run_guardrails(context.latest_user_message)
        if guardrail.blocked:
            return self._response(
                reply=guardrail.reply,
                recommendations=[],
                end_of_conversation=guardrail.end_of_conversation,
            )

        if self._is_comparison_request(context.latest_user_message):
            return self._handle_comparison(context.latest_user_message)

        if len(context.informative_tokens) < self.min_context_signals:
            return self._response(
                reply=self._build_clarifying_question(context),
                recommendations=[],
                end_of_conversation=False,
            )

        recommendations = self.catalog_service.search(
            query=context.user_text,
            limit=self.max_recommendations,
        )

        if not recommendations:
            return self._response(
                reply=(
                    "I don't have enough grounded SHL catalog matches yet. "
                    "Please share the role, seniority, and whether you care most about "
                    "technical skills, cognitive ability, or personality fit."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        reply = self._build_recommendation_reply(context, recommendations)
        agent_reply = self._generate_agent_reply(payload)
        if agent_reply:
            reply = agent_reply
        return self._response(
            reply=reply,
            recommendations=[self._to_recommendation(item) for item in recommendations],
            end_of_conversation=False,
        )

    def _build_context(self, payload: ChatRequest) -> ConversationContext:
        user_messages = [message.content for message in payload.messages if message.role.value == "user"]
        latest_user_message = user_messages[-1] if user_messages else ""
        user_text = " ".join(user_messages)
        informative_tokens = {
            token for token in tokenize(user_text) if token not in GENERIC_TOKENS
        }
        has_seniority = any(token in SENIORITY_HINTS for token in informative_tokens)
        return ConversationContext(
            user_text=user_text,
            latest_user_message=latest_user_message,
            informative_tokens=informative_tokens,
            has_seniority=has_seniority,
        )

    def _is_comparison_request(self, message: str) -> bool:
        return any(token in tokenize(message) for token in COMPARE_HINTS)

    def _handle_comparison(self, message: str) -> ChatResponse:
        matches = self.catalog_service.find_named_items(message)
        if len(matches) < 2:
            return self._response(
                reply="Tell me the two SHL assessments you want compared, and I’ll compare them from catalog data.",
                recommendations=[],
                end_of_conversation=False,
            )

        first, second = matches[:2]
        reply = self._generate_agent_reply_from_text(message)
        if not reply:
            reply = (
            f"{first.name} focuses on {self._describe_item(first)}, while {second.name} focuses on "
            f"{self._describe_item(second)}. If you want, I can also suggest when to use one, the other, or both together."
            )
        return self._response(reply=reply, recommendations=[], end_of_conversation=False)

    def _build_clarifying_question(self, context: ConversationContext) -> str:
        if not context.has_seniority:
            return (
                "What role are you hiring for, what seniority level is it, and do you want to assess "
                "technical skills, cognitive ability, personality, or a mix?"
            )
        return "What are the main skills or behaviors this person needs to succeed in the role?"

    def _build_recommendation_reply(
        self,
        context: ConversationContext,
        recommendations: list[CatalogItem],
    ) -> str:
        top_names = ", ".join(item.name for item in recommendations[:3])
        return (
            f"Based on the role details so far, here is a grounded SHL shortlist. "
            f"My strongest initial matches are {top_names}. I can refine this further if you add constraints like seniority, job family, or whether personality testing should be included."
        )

    def _describe_item(self, item: CatalogItem) -> str:
        categories = ", ".join(item.categories[:2]) if item.categories else "the areas in its catalog entry"
        description = normalize_text(item.description)
        if description:
            return f"{categories} with an emphasis on {description}"
        return categories

    def _to_recommendation(self, item: CatalogItem) -> Recommendation:
        return Recommendation(name=item.name, url=item.url, test_type=item.test_type)

    def _response(
        self,
        reply: str,
        recommendations: list[Recommendation],
        end_of_conversation: bool,
    ) -> ChatResponse:
        return ChatResponse(
            reply=reply,
            recommendations=recommendations,
            end_of_conversation=end_of_conversation,
        )

    def _generate_agent_reply(self, payload: ChatRequest) -> str | None:
        if not self.agent_runner:
            return None
        messages = [message.model_dump() for message in payload.messages]
        return self.agent_runner.generate_reply(messages)

    def _generate_agent_reply_from_text(self, text: str) -> str | None:
        if not self.agent_runner:
            return None
        messages: list[dict[str, Any]] = [{"role": "user", "content": text}]
        return self.agent_runner.generate_reply(messages)
