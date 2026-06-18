from __future__ import annotations

from agents.fallback import FallbackAgent
from agents.intent_router import IntentRouterAgent
from agents.result_interpreter import ResultInterpreterAgent
from agents.sql_generator import SQLGeneratorAgent
from messages.messages import (
    InterpreterInput,
    PipelineResult,
    QueryIntent,
    RouterInput,
    SQLGeneratorInput,
)
from tracing.tracing import AgentTracer


class Orchestrator:
    """Runs the 3-agent pipeline with tracing, retries, and fallback."""

    def __init__(
        self,
        router: IntentRouterAgent,
        sql_generator: SQLGeneratorAgent,
        interpreter: ResultInterpreterAgent,
        *,
        tracer: AgentTracer | None = None,
        agent_max_retries: int = 2,
    ) -> None:
        self.router = router
        self.sql_generator = sql_generator
        self.interpreter = interpreter
        self.tracer = tracer or AgentTracer()
        self.fallback = FallbackAgent()
        self.agent_max_retries = agent_max_retries

    def run(self, question: str, conversation_history: list[str] | None = None) -> PipelineResult:
        query_trace = self.tracer.new_query(question)

        # --- Agent 1: Intent Router ---
        router_output = self._run_with_retry(
            query_trace,
            "intent_router",
            lambda: self.router.run(
                RouterInput(question=question, conversation_history=conversation_history or [])
            ),
        )
        if router_output is None:
            result = self.fallback.run(question, reason="intent_router failed after retries")
            self.tracer.write(query_trace)
            return result

        # --- Agent 2: SQL Generator ---
        sql_output = self._run_with_retry(
            query_trace,
            "sql_generator",
            lambda: self.sql_generator.run(
                SQLGeneratorInput(question=question, intent=router_output.intent)
            ),
        )
        if sql_output is None:
            result = self.fallback.run(question, reason="sql_generator failed after retries")
            self.tracer.write(query_trace)
            return result

        # --- Agent 3: Result Interpreter (always called, even on sql failure) ---
        # Pass the error message through so the LLM generates a friendly response
        # instead of surfacing raw SQL errors to the user.
        interp_input = InterpreterInput(
            question=question,
            intent=router_output.intent,
            sql=sql_output.sql,
            rows=sql_output.rows,
            error=sql_output.message if not sql_output.success else None,
        )

        interp_output = self._run_with_retry(
            query_trace,
            "result_interpreter",
            lambda: self.interpreter.run(interp_input),
        )

        if interp_output is None:
            # Interpreter itself failed — return best-effort response
            self.tracer.write(query_trace)
            return PipelineResult(
                status="success" if sql_output.success else "error",
                question=question,
                intent=router_output.intent,
                sql=sql_output.sql,
                rows=sql_output.rows,
                summary=(
                    "Query completed successfully (summary unavailable)."
                    if sql_output.success
                    else sql_output.message
                ),
                chart_type="table" if sql_output.success else "none",
                message="result_interpreter failed after retries.",
            )

        self.tracer.write(query_trace)
        return PipelineResult(
            status="success" if sql_output.success else "error",
            question=question,
            intent=router_output.intent,
            sql=sql_output.sql,
            rows=sql_output.rows,
            summary=interp_output.summary,
            chart_type=interp_output.chart_type,
            message="ok",
        )

    def _run_with_retry(self, query_trace, agent_name: str, fn):
        """Runs an agent step, retrying on exception, recording every attempt in the trace."""
        for attempt in range(1, self.agent_max_retries + 1):
            with query_trace.step(f"{agent_name}_attempt_{attempt}") as step:
                try:
                    output = fn()
                    step.record_output(output)
                    return output
                except Exception as exc:  # noqa: BLE001 - intentional: never crash the pipeline
                    step.record_output({"error": str(exc)})
        return None