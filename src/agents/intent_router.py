from __future__ import annotations

from infastructure.llm.llm_client import GroqLLMClient
from ..messages import QueryIntent, RouterInput, RouterOutput

ROUTER_SYSTEM_PROMPT = (
    "You classify hospital analytics questions into exactly one category:\n"
    "- aggregation: counts, sums, averages, totals\n"
    "- comparison: comparing groups (e.g. 'highest', 'vs', 'top N')\n"
    "- trend: anything over time (monthly, trend, growth)\n"
    "- lookup: retrieving specific records/details\n"
    "- unknown: anything else\n\n"
    "Respond with EXACTLY two lines:\n"
    "INTENT: <one of aggregation|comparison|trend|lookup|unknown>\n"
    "REASON: <one short sentence>"
)


class IntentRouterAgent:
    """Agent 1: classifies the user question into a QueryIntent."""

    def __init__(self, llm_client: GroqLLMClient) -> None:
        self.llm_client = llm_client

    def run(self, input_obj: RouterInput) -> RouterOutput:
        user_prompt = f"Question: {input_obj.question}"
        if input_obj.conversation_history:
            history = "\n".join(input_obj.conversation_history[-3:])
            user_prompt = f"Recent conversation:\n{history}\n\n{user_prompt}"

        response = self.llm_client.complete(
            system_prompt=ROUTER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        intent, reason = _parse_router_response(response.text)
        return RouterOutput(question=input_obj.question, intent=intent, reasoning=reason)


def _parse_router_response(text: str) -> tuple[QueryIntent, str]:
    intent = QueryIntent.UNKNOWN
    reason = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("INTENT:"):
            value = line.split(":", 1)[1].strip().lower()
            try:
                intent = QueryIntent(value)
            except ValueError:
                intent = QueryIntent.UNKNOWN
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return intent, reason