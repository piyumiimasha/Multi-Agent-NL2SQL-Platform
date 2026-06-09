from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ddl_parser import parse_schema_ddl
from .prompt import PromptBundle, SchemaAwarePromptBuilder
from .schema import PostgresSchemaIntrospector, SchemaSnapshot


@dataclass
class NL2SQLPromptComposer:
    schema: SchemaSnapshot
    prompt_builder: SchemaAwarePromptBuilder

    @classmethod
    def from_database_url(cls, database_url: str, *, sample_row_limit: int = 3, max_tables: int = 6) -> "NL2SQLPromptComposer":
        schema = PostgresSchemaIntrospector(database_url, sample_row_limit=sample_row_limit).load()
        return cls(schema=schema, prompt_builder=SchemaAwarePromptBuilder(max_tables=max_tables, sample_row_limit=sample_row_limit))

    @classmethod
    def from_env(cls, env_path: str | Path = ".env", *, sample_row_limit: int = 3, max_tables: int = 6) -> "NL2SQLPromptComposer":
        schema = PostgresSchemaIntrospector.from_env(env_path, sample_row_limit=sample_row_limit).load()
        return cls(schema=schema, prompt_builder=SchemaAwarePromptBuilder(max_tables=max_tables, sample_row_limit=sample_row_limit))

    @classmethod
    def from_schema_ddl(cls, ddl_text: str, *, max_tables: int = 6) -> "NL2SQLPromptComposer":
        schema = parse_schema_ddl(ddl_text)
        return cls(schema=schema, prompt_builder=SchemaAwarePromptBuilder(max_tables=max_tables))

    def compose(self, question: str) -> PromptBundle:
        return self.prompt_builder.build(question, self.schema)