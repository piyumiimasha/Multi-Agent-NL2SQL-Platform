from __future__ import annotations

import json

from infastructure.llm.llm_client import GroqLLMClient

INSIGHT_SYSTEM = (
    "You are a senior hospital data analyst writing a concise insight for a dashboard panel. "
    "Write exactly 2-3 sentences. Cite specific numbers from the data — no vague generalities. "
    "Keep it factual, professional, and directly relevant to hospital operations."
)


class InsightGenerator:
    def __init__(self, llm_client: GroqLLMClient) -> None:
        self.llm_client = llm_client

    def generate(self, panel_name: str, rows: list[dict], context: str = "") -> str:
        if not rows:
            return "No data available for this panel."

        sample = rows[:20]
        prompt = (
            f"Panel: {panel_name}\n"
            f"Context: {context}\n"
            f"Data (first {len(sample)} rows):\n"
            f"{json.dumps(sample, default=str)}\n\n"
            "Write a 2-3 sentence insight citing specific numbers."
        )

        try:
            response = self.llm_client.complete(
                system_prompt=INSIGHT_SYSTEM,
                user_prompt=prompt,
            )
            return response.text
        except Exception as exc:
            return f"Insight unavailable: {exc}"