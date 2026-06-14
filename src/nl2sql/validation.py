from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
from typing import Iterable
from urllib.parse import quote_plus, urlparse

import psycopg
import sqlparse


class ValidationStatus(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"
    INVALID = "invalid"


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    user_message: str
    reason: str | None = None
    sql: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == ValidationStatus.OK


class SQLValidationError(RuntimeError):
    pass


class SQLSafetyValidator:
    """Reject destructive or multi-statement SQL before it reaches the database."""

    BLOCKED_KEYWORDS = {
        "DELETE",
        "DROP",
        "TRUNCATE",
        "INSERT",
        "UPDATE",
        "ALTER",
        "CREATE",
        "REPLACE",
        "MERGE",
        "GRANT",
        "REVOKE",
        "COMMENT",
        "VACUUM",
        "ANALYZE",
        "EXECUTE",
        "CALL",
        "COPY",
    }

    ALLOWED_FIRST_KEYWORDS = {"SELECT", "WITH", "VALUES"}

    def validate(self, sql_text: str) -> ValidationResult:
        statements = [statement.strip() for statement in sqlparse.split(sql_text) if statement.strip()]

        if not statements:
            return ValidationResult(
                status=ValidationStatus.INVALID,
                user_message="I couldn't build a valid query for that question — try rephrasing it.",
                reason="empty-sql",
            )

        if len(statements) > 1:
            return ValidationResult(
                status=ValidationStatus.BLOCKED,
                user_message="I couldn't build a safe query for that question — try rephrasing it.",
                reason="multiple-statements",
            )

        statement = statements[0]
        first_keyword = _first_keyword(statement)
        if first_keyword not in self.ALLOWED_FIRST_KEYWORDS:
            return ValidationResult(
                status=ValidationStatus.BLOCKED,
                user_message="I couldn't build a safe query for that question — try rephrasing it.",
                reason=f"disallowed-statement:{first_keyword or 'unknown'}",
            )

        upper_sql = statement.upper()
        for keyword in self.BLOCKED_KEYWORDS:
            if keyword in upper_sql:
                return ValidationResult(
                    status=ValidationStatus.BLOCKED,
                    user_message="I couldn't build a safe query for that question — try rephrasing it.",
                    reason=f"blocked-keyword:{keyword}",
                )

        return ValidationResult(status=ValidationStatus.OK, user_message="SQL passed safety checks.", sql=statement)


class SQLSyntaxValidator:
    """Validate SQL syntax and schema references by running EXPLAIN against the database."""

    def __init__(self, database_url: str, *, timeout_seconds: int = 15) -> None:
        self.database_url = database_url
        self.timeout_seconds = timeout_seconds

    def validate(self, sql_text: str) -> ValidationResult:
        safety = SQLSafetyValidator().validate(sql_text)
        if not safety.ok:
            return safety

        statement = safety.sql or sql_text.strip()
        try:
            with psycopg.connect(self.database_url, connect_timeout=self.timeout_seconds) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"EXPLAIN {statement}")
            return ValidationResult(status=ValidationStatus.OK, user_message="SQL is valid.", sql=statement)
        except psycopg.Error as exc:
            return ValidationResult(
                status=ValidationStatus.INVALID,
                user_message="I couldn't build a valid query for that question — try rephrasing it.",
                reason=exc.__class__.__name__,
            )


class SQLValidationGatekeeper:
    """High-level helper that exposes a single safe validation entrypoint."""

    def __init__(self, database_url: str | None = None, *, connect_timeout: int = 15) -> None:
        self.database_url = database_url
        self.connect_timeout = connect_timeout
        self.safety = SQLSafetyValidator()

    @classmethod
    def from_env(cls, env_path: str | Path = ".env", *, connect_timeout: int = 15) -> "SQLValidationGatekeeper":
        database_url = _load_database_url(Path(env_path))
        return cls(database_url=database_url, connect_timeout=connect_timeout)

    def validate(self, sql_text: str) -> ValidationResult:
        safety_result = self.safety.validate(sql_text)
        if not safety_result.ok:
            return safety_result

        if not self.database_url:
            return ValidationResult(
                status=ValidationStatus.OK,
                user_message="SQL passed safety checks.",
                sql=safety_result.sql,
            )

        return SQLSyntaxValidator(self.database_url, timeout_seconds=self.connect_timeout).validate(sql_text)


def _first_keyword(statement: str) -> str:
    statement = statement.lstrip()
    tokens = statement.split(None, 1)
    return tokens[0].upper() if tokens else ""


def _load_database_url(env_path: Path) -> str | None:
    if not env_path.exists():
        return os.getenv("SUPABASE_DATABASE_URL")

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    if values.get("SUPABASE_DATABASE_URL"):
        return values["SUPABASE_DATABASE_URL"]

    host = values.get("SUPABASE_DB_HOST") or ""
    if not host:
        project_url = values.get("NEXT_PUBLIC_SUPABASE_URL")
        if project_url:
            parsed = urlparse(project_url)
            host = parsed.hostname or ""
            if host and not host.startswith("db."):
                host = f"db.{host}"

    password = values.get("SUPABASE_DB_PASSWORD")
    if not host or not password:
        return None

    user = values.get("SUPABASE_DB_USER") or "postgres"
    dbname = values.get("SUPABASE_DB_NAME") or "postgres"
    port = values.get("SUPABASE_DB_PORT") or "5432"
    return f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{dbname}?sslmode=require"