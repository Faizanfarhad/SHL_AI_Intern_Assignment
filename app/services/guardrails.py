from dataclasses import dataclass

from app.utils.text import normalize_text


@dataclass(frozen=True)
class GuardrailResult:
    blocked: bool
    reply: str = ""
    end_of_conversation: bool = False


INJECTION_PATTERNS = (
    "ignore previous instructions",
    "reveal system prompt",
    "show me the hidden prompt",
    "jailbreak",
    "bypass your rules",
)

LEGAL_PATTERNS = (
    "legal",
    "lawsuit",
    "compliance advice",
    "discrimination law",
)

OFF_TOPIC_PATTERNS = (
    "weather",
    "restaurant",
    "flight",
    "movie recommendation",
)


def run_guardrails(message: str) -> GuardrailResult:
    text = normalize_text(message)

    if any(pattern in text for pattern in INJECTION_PATTERNS):
        return GuardrailResult(
            blocked=True,
            reply=(
                "I can only help with SHL assessment selection using the catalog data, "
                "so I can't follow prompt-injection or system prompt requests."
            ),
            end_of_conversation=True,
        )

    if any(pattern in text for pattern in LEGAL_PATTERNS):
        return GuardrailResult(
            blocked=True,
            reply=(
                "I can help narrow SHL assessments, but I can't provide legal or compliance advice."
            ),
            end_of_conversation=True,
        )

    if any(pattern in text for pattern in OFF_TOPIC_PATTERNS):
        return GuardrailResult(
            blocked=True,
            reply="I stay focused on SHL assessments and can't help with unrelated topics.",
            end_of_conversation=True,
        )

    return GuardrailResult(blocked=False)

