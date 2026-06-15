from __future__ import annotations

import json

from ..llm_client import GroqLLMClient
from ..messages import InterpreterInput, InterpreterOutput, QueryIntent

INTERPRETER_SYSTEM_PROMPT = (
    "You are a hospital data analyst. Given a question, the SQL that answered it, "
    "and the resulting rows, write a 2-3 sentence plain-English summary citing "
    "specific numbers from the data. Then suggest ONE chart type.\n\n"
    "Respond as exactly these lines:\n"
    "SUMMARY: <2-3 sentences with real numbers>\n"
    "CHART: <one of bar|line|pie|table|none>\n"
    "ANOMALIES: <comma-separated short notes, or 'none'>"
)


class ResultInterpreterAgent:
    """Agent 3: turns raw SQL result rows into a natural-language summary + chart suggestion."""

    def __init__(self, llm_client: GroqLLMClient, *, max_rows_in_prompt: int = 25) -> None:
        self.llm_client = llm_client
        self.max_rows_in_prompt = max_rows_in_prompt

    def run(self, input_obj: InterpreterInput) -> InterpreterOutput:
        if not input_obj.rows:
            return InterpreterOutput(
                summary="The query ran successfully but returned no rows.",
                chart_type="none",
                anomalies=["empty result set"],
            )

        sample_rows = input_obj.rows[: self.max_rows_in_prompt]
        user_prompt = (
            f"Question: {input_obj.question}\n"
            f"Intent: {input_obj.intent.value}\n"
            f"SQL: {input_obj.sql}\n"
            f"Rows (showing {len(sample_rows)} of {len(input_obj.rows)}):\n"
            f"{json.dumps(sample_rows, default=str)}"
        )

        response = self.llm_client.complete(
            system_prompt=INTERPRETER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return _parse_interpreter_response(response.text)


def _parse_interpreter_response(text: str) -> InterpreterOutput:
    summary = ""
    chart_type = "table"
    anomalies: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CHART:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in {"bar", "line", "pie", "table", "none"}:
                chart_type = value
        elif line.upper().startswith("ANOMALIES:"):
            value = line.split(":", 1)[1].strip()
            if value.lower() != "none":
                anomalies = [a.strip() for a in value.split(",") if a.strip()]

    if not summary:
        summary = "Query completed successfully."

    return InterpreterOutput(summary=summary, chart_type=chart_type, anomalies=anomalies)