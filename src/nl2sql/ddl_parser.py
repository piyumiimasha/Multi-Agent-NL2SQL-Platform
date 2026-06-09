from __future__ import annotations

import re
from collections import OrderedDict

from .schema import ColumnInfo, ForeignKeyInfo, SchemaSnapshot, TableSchema


CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s*\((?P<body>.*?)\);",
    re.IGNORECASE | re.DOTALL,
)

FOREIGN_KEY_RE = re.compile(
    r"FOREIGN\s+KEY\s*\((?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\)\s+REFERENCES\s+(?:public\.)?(?P<table>[a-zA-Z_][a-zA-Z0-9_]*)\s*\((?P<ref_column>[a-zA-Z_][a-zA-Z0-9_]*)\)",
    re.IGNORECASE,
)


def parse_schema_ddl(ddl_text: str) -> SchemaSnapshot:
    snapshot = SchemaSnapshot()

    for match in CREATE_TABLE_RE.finditer(ddl_text):
        table_name = match.group("table")
        body = match.group("body")
        columns: list[ColumnInfo] = []
        foreign_keys: list[ForeignKeyInfo] = []

        for raw_line in _split_table_body(body):
            line = raw_line.strip().rstrip(",")
            if not line:
                continue

            fk_match = FOREIGN_KEY_RE.search(line)
            if fk_match:
                foreign_keys.append(
                    ForeignKeyInfo(
                        column_name=fk_match.group("column"),
                        referenced_table=fk_match.group("table"),
                        referenced_column=fk_match.group("ref_column"),
                    )
                )
                continue

            if line.upper().startswith("CONSTRAINT "):
                continue

            column = _parse_column_definition(line)
            if column:
                columns.append(column)

        snapshot.tables[table_name] = TableSchema(
            name=table_name,
            columns=columns,
            foreign_keys=foreign_keys,
            sample_rows=[],
        )

    return snapshot


def _split_table_body(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _parse_column_definition(line: str) -> ColumnInfo | None:
    tokens = line.split()
    if len(tokens) < 2:
        return None

    name = tokens[0].strip('"')
    if name.upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
        return None

    type_tokens: list[str] = []
    for token in tokens[1:]:
        upper = token.upper()
        if upper in {"NOT", "NULL", "DEFAULT", "CONSTRAINT", "PRIMARY", "REFERENCES", "UNIQUE", "CHECK", "COLLATE"}:
            break
        type_tokens.append(token)

    if not type_tokens:
        return None

    data_type = " ".join(type_tokens)
    is_nullable = "NOT NULL" not in line.upper()
    default = None
    default_match = re.search(r"DEFAULT\s+(?P<default>.+?)(?:\s+NOT\s+NULL|\s+CONSTRAINT|\s+PRIMARY\s+KEY|$)", line, re.IGNORECASE)
    if default_match:
        default = default_match.group("default").strip().rstrip(",")

    return ColumnInfo(name=name, data_type=data_type, is_nullable=is_nullable, default=default)