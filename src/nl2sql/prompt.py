from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .schema import SchemaSnapshot, TableSchema


@dataclass(frozen=True)
class PromptBundle:
    question: str
    system_prompt: str
    user_prompt: str
    selected_tables: list[str]


class SchemaAwarePromptBuilder:
    def __init__(self, *, max_tables: int = 6, sample_row_limit: int = 3) -> None:
        self.max_tables = max_tables
        self.sample_row_limit = sample_row_limit

    def build(self, question: str, schema: SchemaSnapshot) -> PromptBundle:
        selected_tables = self.select_tables(question, schema)
        schema_context = self.render_schema_context(schema, selected_tables)
        system_prompt = self.render_system_prompt()
        user_prompt = self.render_user_prompt(question, schema_context)
        return PromptBundle(
            question=question,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            selected_tables=selected_tables,
        )

    def select_tables(self, question: str, schema: SchemaSnapshot) -> list[str]:
        question_tokens = set(_tokenize(question))
        scored: list[tuple[int, str]] = []

        for table_name in schema.table_names():
            table = schema.get(table_name)
            if not table:
                continue
            score = _score_table(question_tokens, table)
            scored.append((score, table_name))

        scored.sort(key=lambda item: (-item[0], item[1]))
        chosen = [name for score, name in scored if score > 0][: self.max_tables]

        if not chosen and scored:
            chosen = [scored[0][1]]

        expanded: list[str] = []
        seen = set()
        for table_name in chosen:
            if table_name not in seen:
                seen.add(table_name)
                expanded.append(table_name)
            for neighbor in schema.neighbors_for(table_name):
                if neighbor not in seen:
                    seen.add(neighbor)
                    expanded.append(neighbor)

        return expanded[: max(self.max_tables, len(expanded))]

    def render_system_prompt(self) -> str:
        return (
            "You are a schema-aware NL2SQL engine for MediCore Hospital. "
            "Generate a single valid PostgreSQL query that answers the user's question. "
            "Use only tables, columns, and joins present in the provided schema context. "
            "Never invent table names, column names, or relationships. "
            "Prefer explicit JOINs that follow the foreign keys. "
            "Return SQL only, with no markdown, no prose, and no explanations. "
            "If the question cannot be answered safely from the schema, return a short clarification question only."
        )

    def render_user_prompt(self, question: str, schema_context: str) -> str:
        return (
            f"User question:\n{question}\n\n"
            f"Schema context:\n{schema_context}\n\n"
            "Rules:\n"
            "- Use only the schema context above.\n"
            "- Keep the SQL programmatic and executable.\n"
            "- Prefer readable aliases and deterministic ordering when needed.\n"
            "- Do not include commentary, code fences, or explanations."
        )

    def render_schema_context(self, schema: SchemaSnapshot, table_names: Iterable[str]) -> str:
        lines: list[str] = []
        for table_name in table_names:
            table = schema.get(table_name)
            if not table:
                continue
            lines.append(_render_table(table))
        return "\n\n".join(lines)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _score_table(question_tokens: set[str], table: TableSchema) -> int:
    score = 0
    table_tokens = set(_tokenize(table.name.replace("_", " ")))
    if table_tokens & question_tokens:
        score += 5

    singular = table.name.rstrip("s")
    if singular and singular in question_tokens:
        score += 3

    for column in table.columns:
        column_tokens = set(_tokenize(column.name.replace("_", " ")))
        score += len(column_tokens & question_tokens)

    for fk in table.foreign_keys:
        fk_tokens = set(_tokenize(fk.referenced_table.replace("_", " ")))
        if fk_tokens & question_tokens:
            score += 2

    return score


def _render_table(table: TableSchema) -> str:
    column_lines = []
    for column in table.columns:
        nullable = "nullable" if column.is_nullable else "not null"
        default = f", default={column.default}" if column.default else ""
        column_lines.append(f"  - {column.name} ({column.data_type}, {nullable}{default})")

    fk_lines = [
        f"  - {fk.column_name} -> {fk.referenced_table}.{fk.referenced_column}"
        for fk in table.foreign_keys
    ]

    sample_lines = [f"  - {row}" for row in table.sample_rows] if table.sample_rows else ["  - <no rows>"]

    parts = [f"Table {table.name}:", "Columns:", *column_lines]
    if fk_lines:
        parts.extend(["Foreign keys:", *fk_lines])
    parts.extend(["Sample rows:", *sample_lines])
    return "\n".join(parts)