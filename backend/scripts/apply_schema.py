#!/usr/bin/env python3
"""Apply SQL migrations using Supabase service role + optional direct Postgres URL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "") or os.environ.get("SUPABASE_DB_URL", "")
SQL_FILE = BACKEND_ROOT / "sql" / "001_worksheet_schema.sql"


def apply_via_psycopg2(sql: str) -> None:
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()


def apply_via_supabase_rpc(sql: str) -> bool:
    """Try common Supabase SQL RPC helpers if present in the project."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return False
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    for rpc in ("exec_sql", "run_sql", "execute_sql"):
        try:
            resp = httpx.post(
                f"{SUPABASE_URL}/rest/v1/rpc/{rpc}",
                headers=headers,
                json={"query": sql},
                timeout=60.0,
            )
        except httpx.ConnectError as exc:
            print(f"Cannot reach Supabase ({SUPABASE_URL}): {exc}")
            return False
        if resp.status_code == 200:
            return True
        if resp.status_code not in (404, 400):
            print(f"rpc/{rpc} -> {resp.status_code}: {resp.text[:200]}")
    return False


def verify_tables() -> list[str]:
    from supabase import create_client

    sb = create_client(SUPABASE_URL, SERVICE_KEY)
    missing = []
    for table in ("chore_app_state", "tasks", "worksheet_entries", "daily_generated_questions"):
        try:
            sb.table(table).select("*").limit(1).execute()
        except Exception:
            missing.append(table)
    return missing


def main() -> int:
    if not SQL_FILE.exists():
        print(f"Missing SQL file: {SQL_FILE}")
        return 1
    sql = SQL_FILE.read_text(encoding="utf-8")

    if DATABASE_URL:
        print("Applying schema via DATABASE_URL …")
        apply_via_psycopg2(sql)
    elif apply_via_supabase_rpc(sql):
        print("Applied schema via Supabase SQL RPC.")
    else:
        print(
            "Could not apply DDL automatically. Set DATABASE_URL in backend/.env "
            "(Supabase → Settings → Database → connection string) and re-run, "
            "or paste backend/sql/001_worksheet_schema.sql into the Supabase SQL editor."
        )
        return 2

    missing = verify_tables()
    if missing:
        print("Still missing tables:", ", ".join(missing))
        return 3

    print("Schema OK:", "chore_app_state, tasks, worksheet_entries, daily_generated_questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
