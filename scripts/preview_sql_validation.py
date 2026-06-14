from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nl2sql.validation import SQLValidationGatekeeper


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SQL with safety and syntax checks.")
    parser.add_argument("sql", help="SQL text to validate.")
    parser.add_argument("--env", default=".env", help="Path to the environment file.")
    args = parser.parse_args()

    gatekeeper = SQLValidationGatekeeper.from_env(args.env)
    result = gatekeeper.validate(args.sql)
    print(result.status.value)
    print(result.user_message)
    if result.reason:
        print(result.reason)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())