from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nl2sql.engine import NL2SQLPromptComposer


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview the schema-aware NL2SQL prompt.")
    parser.add_argument("question", help="Natural language question to convert into prompt context.")
    parser.add_argument("--env", default=".env", help="Path to the environment file.")
    parser.add_argument("--ddl-file", default=str(Path("data") / "schema_reference.sql"), help="Optional DDL file to use instead of a live database.")
    parser.add_argument("--max-tables", type=int, default=6, help="Maximum number of tables to include before FK expansion.")
    parser.add_argument("--sample-row-limit", type=int, default=3, help="Number of sample rows to fetch per table.")
    args = parser.parse_args()

    ddl_path = Path(args.ddl_file)
    if ddl_path.exists():
        composer = NL2SQLPromptComposer.from_schema_ddl(ddl_path.read_text(encoding="utf-8"), max_tables=args.max_tables)
    else:
        composer = NL2SQLPromptComposer.from_env(
            args.env,
            sample_row_limit=args.sample_row_limit,
            max_tables=args.max_tables,
        )
    bundle = composer.compose(args.question)

    print("=== SYSTEM PROMPT ===")
    print(bundle.system_prompt)
    print()
    print("=== USER PROMPT ===")
    print(bundle.user_prompt)
    print()
    print("=== SELECTED TABLES ===")
    print(", ".join(bundle.selected_tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())