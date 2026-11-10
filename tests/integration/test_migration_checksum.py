"""Migration checksum regression tests (M10)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set",
)

_RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "migrations" / "runner.py"
_MIGRATIONS = Path(__file__).resolve().parents[2] / "sql" / "migrations"


def _load_runner(tmp_path, migrations_dir):
    import importlib.util

    spec = importlib.util.spec_from_file_location("bitemporal_migrations_runner", _RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.MIGRATIONS_DIR = migrations_dir
    return module


def test_clean_rerun_is_noop() -> None:
    dsn = os.environ["DATABASE_URL"]
    runner = _load_runner(Path("/tmp/x"), _MIGRATIONS)
    second = runner.run(dsn)
    assert second == []


def test_checksum_tamper_fails_loudly_without_touching_db(tmp_path) -> None:
    tampered = tmp_path / "migrations"
    shutil.copytree(_MIGRATIONS, tampered)
    target = tampered / "001_initial_schema.sql"
    target.write_text(target.read_text(encoding="utf-8") + "\n-- tamper\n", encoding="utf-8")
    runner = _load_runner(tmp_path, tampered)
    dsn = os.environ["DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.txn_business")
            before_business = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.migration")
            before_migrations = cur.fetchone()[0]
    with pytest.raises(RuntimeError, match="Migration checksum mismatch"):
        runner.run(dsn)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.txn_business")
            after_business = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.migration")
            after_migrations = cur.fetchone()[0]
    assert after_business == before_business
    assert after_migrations == before_migrations
