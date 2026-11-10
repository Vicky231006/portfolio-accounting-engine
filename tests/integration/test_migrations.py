"""Database integration tests for the M1 migration foundation (requires DATABASE_URL)."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; integration tests require the Docker PostgreSQL 16 service",
)

EXPECTED_CORE_TABLES = {
    "migration",
    "account",
    "nav_snapshot",
    "nav_observation",
    "report_snapshot",
    "nav_revision_conflict",
}

_RUNNER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrations" / "runner.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("bitemporal_migrations_runner", _RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_expected_core_tables_exist() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'core'")
            tables = {row[0] for row in cur.fetchall()}
    assert EXPECTED_CORE_TABLES <= tables


def test_migrations_apply_cleanly_and_are_idempotent() -> None:
    runner = _load_runner()
    runner.run()
    second = runner.run()
    assert second == []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT migration_name FROM core.migration ORDER BY migration_id")
            applied = [row[0] for row in cur.fetchall()]
    migration_files = sorted(p.name for p in runner.MIGRATIONS_DIR.glob("*.sql"))
    assert applied == migration_files
