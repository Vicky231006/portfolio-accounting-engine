"""Minimal versioned migration runner (M1).

Applies SQL files from ``sql/migrations`` in sorted filename order, tracking
applied migrations (name + content checksum) in ``core.migration``. Requires
``DATABASE_URL``. Safe to re-run: applied migrations are skipped and checksum
mismatches fail loudly.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


def run(dsn: str | None = None) -> list[str]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        cur = conn.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS core")
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute("CREATE SCHEMA IF NOT EXISTS staging")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS core.migration (
                migration_id BIGSERIAL PRIMARY KEY,
                migration_name VARCHAR(255) NOT NULL UNIQUE,
                checksum VARCHAR(64) NOT NULL DEFAULT '',
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            "SELECT migration_name, checksum FROM core.migration ORDER BY migration_id"
        )
        applied = {row[0]: row[1] for row in cur.fetchall()}
        applied_names: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            name = path.name
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if name in applied:
                if applied[name] != digest:
                    raise RuntimeError(
                        f"Migration checksum mismatch for {name}: recorded {applied[name]}, computed {digest}"
                    )
                continue
            sql_text = path.read_text(encoding="utf-8")
            cur.execute(sql_text)
            cur.execute(
                "INSERT INTO core.migration (migration_name, checksum) VALUES (%s, %s)",
                (name, digest),
            )
            applied_names.append(name)
        conn.commit()
    return applied_names


if __name__ == "__main__":
    print("Applied:", run())
