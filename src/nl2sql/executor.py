from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .validation import _load_database_url  # reuse existing env loader


@dataclass
class QueryExecutionResult:
    success: bool
    rows: list[dict[str, object]]
    row_count: int
    message: str


class SQLQueryExecutor:
    """Executes validated, read-only SQL and returns result rows."""

    def __init__(self, database_url: str, *, row_limit: int = 500, timeout_seconds: int = 15) -> None:
        self.database_url = database_url
        self.row_limit = row_limit
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, env_path: str | Path = ".env", **kwargs: object) -> "SQLQueryExecutor":
        database_url = _load_database_url(Path(env_path))
        if not database_url:
            raise RuntimeError("Missing database connection string in .env")
        return cls(database_url, **kwargs)

    def execute(self, sql_text: str) -> QueryExecutionResult:
        try:
            with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=self.timeout_seconds, prepare_threshold=None) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_text)
                    rows = cur.fetchmany(self.row_limit)
                    return QueryExecutionResult(
                        success=True,
                        rows=[dict(r) for r in rows],
                        row_count=len(rows),
                        message=f"Returned {len(rows)} row(s).",
                    )
        except psycopg.Error as exc:
            return QueryExecutionResult(
                success=False,
                rows=[],
                row_count=0,
                message=f"Query execution failed: {exc.__class__.__name__}",
            )