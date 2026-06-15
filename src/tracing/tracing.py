from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return obj


class AgentTracer:
    """Logs per-agent input/output/latency/tokens to traces/<query_id>.json."""

    def __init__(self, traces_dir: str | Path = "traces") -> None:
        self.traces_dir = Path(traces_dir)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def new_query(self, question: str) -> "QueryTrace":
        query_id = uuid.uuid4().hex[:12]
        return QueryTrace(query_id=query_id, question=question, tracer=self)

    def write(self, query_trace: "QueryTrace") -> Path:
        path = self.traces_dir / f"{query_trace.query_id}.json"
        path.write_text(json.dumps(query_trace.to_dict(), indent=2, default=str))
        return path


class QueryTrace:
    def __init__(self, query_id: str, question: str, tracer: AgentTracer) -> None:
        self.query_id = query_id
        self.question = question
        self.tracer = tracer
        self.steps: list[dict[str, Any]] = []
        self.started_at = time.time()

    def step(self, agent_name: str):
        """Context manager: records input/output/latency/tokens for one agent call."""
        return _StepRecorder(self, agent_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "question": self.question,
            "started_at": self.started_at,
            "total_latency_ms": round((time.time() - self.started_at) * 1000, 2),
            "steps": self.steps,
        }


class _StepRecorder:
    def __init__(self, query_trace: QueryTrace, agent_name: str) -> None:
        self.query_trace = query_trace
        self.agent_name = agent_name
        self.input_obj: Any = None
        self.output_obj: Any = None
        self.error: str | None = None
        self.tokens: dict[str, int] | None = None
        self._start = 0.0

    def __enter__(self) -> "_StepRecorder":
        self._start = time.time()
        return self

    def record_input(self, obj: Any) -> None:
        self.input_obj = obj

    def record_output(self, obj: Any) -> None:
        self.output_obj = obj

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.tokens = {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        latency_ms = round((time.time() - self._start) * 1000, 2)
        if exc_val is not None:
            self.error = f"{exc_type.__name__}: {exc_val}"

        self.query_trace.steps.append(
            {
                "agent": self.agent_name,
                "latency_ms": latency_ms,
                "input": _to_jsonable(self.input_obj),
                "output": _to_jsonable(self.output_obj),
                "tokens": self.tokens,
                "error": self.error,
            }
        )
        # Swallow the exception here so the orchestrator's retry/fallback logic
        # (Part 2c) decides what happens next — tracing shouldn't hide errors,
        # but it shouldn't crash the pipeline either.
        return True if exc_val is not None else False