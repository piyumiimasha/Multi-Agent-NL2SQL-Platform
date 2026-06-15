from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote_plus, urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    default: str | None = None


@dataclass(frozen=True)
class ForeignKeyInfo:
    column_name: str
    referenced_table: str
    referenced_column: str


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)
    sample_rows: list[dict[str, object]] = field(default_factory=list)


@dataclass
class SchemaSnapshot:
    tables: dict[str, TableSchema] = field(default_factory=dict)

    def table_names(self) -> list[str]:
        return sorted(self.tables)

    def get(self, table_name: str) -> TableSchema | None:
        return self.tables.get(table_name)

    def neighbors_for(self, table_name: str) -> set[str]:
        table = self.get(table_name)
        if not table:
            return set()
        neighbors = {fk.referenced_table for fk in table.foreign_keys}
        for other in self.tables.values():
            for fk in other.foreign_keys:
                if fk.referenced_table == table_name:
                    neighbors.add(other.name)
        neighbors.discard(table_name)
        return neighbors


class PostgresSchemaIntrospector:
    def __init__(
        self,
        database_url: str,
        *,
        schema_name: str = "public",
        sample_row_limit: int = 3,
        include_tables: Sequence[str] | None = None,
        exclude_tables: Sequence[str] | None = None,
    ) -> None:
        self.database_url = database_url
        self.schema_name = schema_name
        self.sample_row_limit = sample_row_limit
        self.include_tables = set(include_tables or [])
        self.exclude_tables = set(exclude_tables or [])

    @classmethod
    def from_env(cls, env_path: str | Path = ".env", **kwargs: object) -> "PostgresSchemaIntrospector":
        env_file = Path(env_path)
        database_url = _load_database_url(env_file)
        if not database_url:
            raise RuntimeError(
                "Missing database connection string. Set SUPABASE_DATABASE_URL or NEXT_PUBLIC_SUPABASE_URL plus Supabase DB host/password values."
            )
        return cls(database_url, **kwargs)

    def load(self) -> SchemaSnapshot:
        snapshot = SchemaSnapshot()
        with psycopg.connect(self.database_url, row_factory=dict_row, prepare_threshold=None) as connection:
            with connection.cursor() as cursor:
                table_names = self._load_table_names(cursor)
                foreign_keys = self._load_foreign_keys(cursor)

                for table_name in table_names:
                    snapshot.tables[table_name] = TableSchema(
                        name=table_name,
                        columns=self._load_columns(cursor, table_name),
                        foreign_keys=foreign_keys.get(table_name, []),
                        sample_rows=self._load_sample_rows(cursor, table_name),
                    )

        return snapshot

    def _load_table_names(self, cursor: psycopg.Cursor) -> list[str]:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (self.schema_name,),
        )
        table_names = [row["table_name"] for row in cursor.fetchall()]

        if self.include_tables:
            table_names = [name for name in table_names if name in self.include_tables]
        if self.exclude_tables:
            table_names = [name for name in table_names if name not in self.exclude_tables]

        return table_names

    def _load_columns(self, cursor: psycopg.Cursor, table_name: str) -> list[ColumnInfo]:
        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (self.schema_name, table_name),
        )
        columns: list[ColumnInfo] = []
        for row in cursor.fetchall():
            columns.append(
                ColumnInfo(
                    name=row["column_name"],
                    data_type=row["data_type"],
                    is_nullable=row["is_nullable"] == "YES",
                    default=row["column_default"],
                )
            )
        return columns

    def _load_foreign_keys(self, cursor: psycopg.Cursor) -> dict[str, list[ForeignKeyInfo]]:
        cursor.execute(
            """
            SELECT
                kcu.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
            ORDER BY kcu.table_name, kcu.ordinal_position
            """,
            (self.schema_name,),
        )
        foreign_keys: dict[str, list[ForeignKeyInfo]] = {}
        for row in cursor.fetchall():
            foreign_keys.setdefault(row["table_name"], []).append(
                ForeignKeyInfo(
                    column_name=row["column_name"],
                    referenced_table=row["foreign_table_name"],
                    referenced_column=row["foreign_column_name"],
                )
            )
        return foreign_keys

    def _load_sample_rows(self, cursor: psycopg.Cursor, table_name: str) -> list[dict[str, object]]:
        identifier = sql.SQL("{}.{}").format(sql.Identifier(self.schema_name), sql.Identifier(table_name))
        query = sql.SQL("SELECT * FROM {} LIMIT %s").format(identifier)
        cursor.execute(query, (self.sample_row_limit,))
        return [dict(row) for row in cursor.fetchall()]


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

    if os.getenv("SUPABASE_DATABASE_URL"):
        return os.getenv("SUPABASE_DATABASE_URL")

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