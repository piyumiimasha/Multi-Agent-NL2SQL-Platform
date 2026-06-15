from __future__ import annotations

from ..messages import QueryIntent, SQLGeneratorInput, SQLGeneratorOutput
from ..retry_engine import NL2SQLEngine, EngineStatus
from ..executor import SQLQueryExecutor

INTENT_HINTS = {
    QueryIntent.AGGREGATION: "This is an aggregation question — likely needs GROUP BY, COUNT/SUM/AVG.",
    QueryIntent.COMPARISON: "This is a comparison question — likely needs ORDER BY with a LIMIT, or multiple groups compared side by side.",
    QueryIntent.TREND: "This is a trend question — likely needs date truncation (DATE_TRUNC) and grouping by time period.",
    QueryIntent.LOOKUP: "This is a lookup question — likely needs a filtered SELECT with WHERE on specific identifiers.",
    QueryIntent.UNKNOWN: "",
}


class SQLGeneratorAgent:
    """Agent 2: generates validated SQL (Part 1c) and executes it (Part 1 executor)."""

    def __init__(self, engine: NL2SQLEngine, executor: SQLQueryExecutor) -> None:
        self.engine = engine
        self.executor = executor

    def run(self, input_obj: SQLGeneratorInput) -> SQLGeneratorOutput:
        hint = INTENT_HINTS.get(input_obj.intent, "")
        question = f"{input_obj.question}\n\n[Routing hint: {hint}]" if hint else input_obj.question

        engine_result = self.engine.generate_sql(question)

        if engine_result.status == EngineStatus.SUCCESS:
            exec_result = self.executor.execute(engine_result.sql)
            if exec_result.success:
                return SQLGeneratorOutput(
                    success=True,
                    sql=engine_result.sql,
                    rows=exec_result.rows,
                    row_count=exec_result.row_count,
                    message=exec_result.message,
                )
            return SQLGeneratorOutput(
                success=False,
                sql=engine_result.sql,
                rows=[],
                row_count=0,
                message=exec_result.message,
            )

        if engine_result.status == EngineStatus.CLARIFICATION_NEEDED:
            return SQLGeneratorOutput(
                success=False,
                sql=None,
                rows=[],
                row_count=0,
                message=engine_result.message,  # the clarifying question
            )

        # EngineStatus.FAILED (e.g. blocked destructive SQL)
        return SQLGeneratorOutput(
            success=False,
            sql=None,
            rows=[],
            row_count=0,
            message=engine_result.message,
        )