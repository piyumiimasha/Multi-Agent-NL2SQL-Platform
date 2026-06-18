from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(str, Enum):
    AGGREGATION = "aggregation"
    COMPARISON = "comparison"
    TREND = "trend"
    LOOKUP = "lookup"
    UNKNOWN = "unknown"


# ---- Intent Router ----

@dataclass(frozen=True)
class RouterInput:
    question: str
    conversation_history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RouterOutput:
    question: str
    intent: QueryIntent
    reasoning: str


# ---- SQL Generator ----

@dataclass(frozen=True)
class SQLGeneratorInput:
    question: str
    intent: QueryIntent


@dataclass(frozen=True)
class SQLGeneratorOutput:
    success: bool
    sql: str | None
    rows: list[dict[str, object]]
    row_count: int
    message: str


# ---- Result Interpreter ----

@dataclass(frozen=True)
class InterpreterInput:
    question: str
    intent: QueryIntent
    sql: str | None
    rows: list[dict[str, object]]
    error: str | None = None   


@dataclass(frozen=True)
class InterpreterOutput:
    summary: str
    chart_type: str  # "bar" | "line" | "pie" | "table" | "none"
    anomalies: list[str] = field(default_factory=list)


# ---- Pipeline-level result ----

@dataclass(frozen=True)
class PipelineResult:
    status: str  # "success" | "fallback" | "error"
    question: str
    intent: QueryIntent | None
    sql: str | None
    rows: list[dict[str, object]]
    summary: str
    chart_type: str
    message: str