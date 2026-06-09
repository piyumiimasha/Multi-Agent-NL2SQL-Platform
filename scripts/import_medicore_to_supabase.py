from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urlparse, urlsplit

import psycopg
import sqlparse


def load_dotenv_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        current_key, value = line.split("=", 1)
        if current_key.strip() != key:
            continue

        return value.strip().strip('"').strip("'")

    return None


def load_supabase_host(env_path: Path) -> str:
    value = load_dotenv_value(env_path, "NEXT_PUBLIC_SUPABASE_URL")
    if value:
        parsed = urlparse(value)
        if parsed.hostname:
            host = parsed.hostname
            if not host.startswith("db."):
                host = f"db.{host}"
            return host
    raise RuntimeError(
        "Could not determine the Supabase host from .env. Set SUPABASE_DB_HOST or SUPABASE_DATABASE_URL."
    )


def build_database_url(args: argparse.Namespace, env_path: Path) -> str:
    if args.database_url:
        return args.database_url

    database_url = os.getenv("SUPABASE_DATABASE_URL")
    if database_url:
        return database_url

    host = args.db_host or os.getenv("SUPABASE_DB_HOST")
    if not host:
        host = load_supabase_host(env_path)

    hostaddr = args.db_hostaddr or os.getenv("SUPABASE_DB_HOSTADDR") or load_dotenv_value(env_path, "SUPABASE_DB_HOSTADDR")

    user = args.db_user or os.getenv("SUPABASE_DB_USER") or load_dotenv_value(env_path, "SUPABASE_DB_USER") or "postgres"
    password = args.db_password or os.getenv("SUPABASE_DB_PASSWORD") or load_dotenv_value(env_path, "SUPABASE_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "Missing database password. Set SUPABASE_DB_PASSWORD or pass --db-password."
        )

    dbname = args.db_name or os.getenv("SUPABASE_DB_NAME") or load_dotenv_value(env_path, "SUPABASE_DB_NAME") or "postgres"
    port = args.db_port or os.getenv("SUPABASE_DB_PORT") or load_dotenv_value(env_path, "SUPABASE_DB_PORT") or "5432"

    base_url = (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{quote_plus(dbname)}?sslmode=require"
    )

    if hostaddr:
        base_url += f"&hostaddr={quote_plus(hostaddr)}"

    return base_url


def iter_sql_statements(file_path: Path) -> Iterable[str]:
    text = file_path.read_text(encoding="utf-8")
    for statement in sqlparse.split(text):
        stripped = statement.strip()
        if stripped:
            yield stripped


def mask_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if not parsed.password:
        return database_url

    username = parsed.username or ""
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    userinfo = username
    if parsed.password:
        userinfo = f"{username}:***"
    return f"{parsed.scheme}://{userinfo}@{host}{parsed.path}?{parsed.query}".rstrip("?")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import the MediCore SQL dump or chunk files into Supabase/PostgreSQL."
    )
    parser.add_argument(
        "--chunks-dir",
        default=str(Path("data") / "medicore_chunks"),
        help="Directory containing part-*.sql files.",
    )
    parser.add_argument(
        "--sql-file",
        default=str(Path("data") / "medicore_data.sql"),
        help="Fallback SQL dump file to import when chunk files are not available.",
    )
    parser.add_argument(
        "--database-url",
        help="Full PostgreSQL connection string. Overrides the env-based settings.",
    )
    parser.add_argument("--db-host", help="Supabase DB host, for example db.<ref>.supabase.co")
    parser.add_argument("--db-hostaddr", help="Resolved IP address for the Supabase DB host.")
    parser.add_argument("--db-user", default="postgres", help="Database user name.")
    parser.add_argument("--db-password", help="Database password.")
    parser.add_argument("--db-name", default="postgres", help="Database name.")
    parser.add_argument("--db-port", default="5432", help="Database port.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without connecting to the database.",
    )
    args = parser.parse_args()

    env_path = Path(".env")
    chunks_dir = Path(args.chunks_dir)
    sql_file = Path(args.sql_file)

    if chunks_dir.exists():
        sql_files = sorted(chunks_dir.glob("part-*.sql"))
    else:
        sql_files = []

    if not sql_files:
        if not sql_file.exists():
            raise SystemExit(f"Neither chunk files nor SQL file were found. Missing: {sql_file}")
        sql_files = [sql_file]

    if args.dry_run:
        for sql_path in sql_files:
            statements = list(iter_sql_statements(sql_path))
            print(f"{sql_path.name}: {len(statements)} statements")
        return 0

    database_url = build_database_url(args, env_path)
    print(f"Database URL: {mask_database_url(database_url)}")

    total_statements = 0
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for sql_path in sql_files:
                statements = list(iter_sql_statements(sql_path))
                print(f"Running {sql_path.name} ({len(statements)} statements)")
                for statement in statements:
                    cursor.execute(statement)
                    total_statements += 1
                connection.commit()

    print(f"Imported {len(sql_files)} files and {total_statements} statements successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())