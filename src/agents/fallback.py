from __future__ import annotations

from messages.messages import PipelineResult, QueryIntent


class FallbackAgent:
    """Returns a safe, friendly response when the pipeline cannot complete normally."""

    def run(self, question: str, *, reason: str, partial_sql: str | None = None) -> PipelineResult:
        if partial_sql:
            message = (
                "I generated a query for this, but couldn't retrieve results "
                "due to a temporary issue. You can try again, or rephrase your "
                "question to be more specific."
            )
        else:
            message = (
                "I wasn't able to answer that question right now. This could be "
                "due to a temporary issue with the analytics service. Please try "
                "again, or rephrase your question — for example, naming a specific "
                "department, doctor, or time period."
            )

        return PipelineResult(
            status="fallback",
            question=question,
            intent=None,
            sql=partial_sql,
            rows=[],
            summary=message,
            chart_type="none",
            message=f"Fallback triggered: {reason}",
        )