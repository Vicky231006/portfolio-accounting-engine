"""FundLens raw-file NAV import CLI (M1, FundLens Option A fallback)."""

from __future__ import annotations

import argparse
import os

import psycopg

from bitemporal_ledger.navigation.fundlens_adapter import FundLensRawNavAdapter


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")
    return dsn


def run_import(source_dir: str, snapshot_name: str) -> dict:
    adapter = FundLensRawNavAdapter(source_dir)
    files = adapter.select_canonical(adapter.discover())
    scan = adapter.scan(files)
    source_file_sha256 = adapter.file_sha256(files[0]) if files else ""
    dsn = _dsn()
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nav_snapshot_id FROM core.nav_snapshot"
                " WHERE snapshot_name = %s AND source_file_sha256 = %s",
                (snapshot_name, source_file_sha256),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO core.nav_snapshot (snapshot_name, source_file_sha256, schema_version)"
                    " VALUES (%s, %s, %s) RETURNING nav_snapshot_id",
                    (snapshot_name, source_file_sha256, "amfi_raw_v1"),
                )
                snapshot_id = cur.fetchone()[0]
            else:
                snapshot_id = row[0]
            cur.execute(
                "SELECT amfi_scheme_code, nav_date FROM core.nav_observation"
                " WHERE nav_snapshot_id = %s",
                (snapshot_id,),
            )
            existing = {(r[0], r[1]) for r in cur.fetchall()}
            inserted = 0
            skipped = 0
            for obs in scan.observations:
                key = (obs.amfi_scheme_code, obs.nav_date)
                if key in existing:
                    skipped += 1
                    continue
                cur.execute(
                    "INSERT INTO core.nav_observation"
                    " (nav_snapshot_id, amfi_scheme_code, nav_date, nav, option_type, source_file_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (snapshot_id, obs.amfi_scheme_code, obs.nav_date, obs.nav, obs.option_type, obs.source_file_sha256),
                )
                inserted += 1
            conflict_inserted = 0
            for scheme_code, nav_date, original_nav, conflicting_nav, source_file_sha256 in scan.rejected_duplicates:
                cur.execute(
                    "INSERT INTO core.nav_revision_conflict"
                    " (nav_snapshot_id, amfi_scheme_code, nav_date, original_nav, conflicting_nav, source_file_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (snapshot_id, scheme_code, nav_date, original_nav, conflicting_nav, source_file_sha256),
                )
                conflict_inserted += 1
            cur.execute(
                "UPDATE core.nav_snapshot"
                " SET row_count = (SELECT count(*) FROM core.nav_observation WHERE nav_snapshot_id = %s),"
                "     min_nav_date = (SELECT min(nav_date) FROM core.nav_observation WHERE nav_snapshot_id = %s),"
                "     max_nav_date = (SELECT max(nav_date) FROM core.nav_observation WHERE nav_snapshot_id = %s)"
                " WHERE nav_snapshot_id = %s",
                (snapshot_id, snapshot_id, snapshot_id, snapshot_id),
            )
        conn.commit()
    return {
        "files": len(files),
        "observations": len(scan.observations),
        "rejected_duplicates": len(scan.rejected_duplicates),
        "inserted": inserted,
        "skipped": skipped,
        "conflicts_recorded": conflict_inserted,
        "snapshot_id": snapshot_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FundLens raw-file NAV import (M1)")
    parser.add_argument("--source-dir", default="/path/to/fundlens/raw_navs")
    parser.add_argument("--snapshot-name", default="amfi_nav_20260101_20261231")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    adapter = FundLensRawNavAdapter(args.source_dir)
    files = adapter.select_canonical(adapter.discover())
    scan = adapter.scan(files)
    source_file_sha256 = adapter.file_sha256(files[0]) if files else ""
    print(
        f"files={len(files)} observations={len(scan.observations)}"
        f" rejected_duplicates={len(scan.rejected_duplicates)}"
    )
    for name, digest in sorted({p.name: adapter.file_sha256(p) for p in files}.items()):
        print(f"{name} {digest}")

    if args.apply:
        result = run_import(args.source_dir, args.snapshot_name)
        print(
            f"applied snapshot={args.snapshot_name} source_file_sha256={source_file_sha256}"
            f" inserted={result['inserted']} skipped={result['skipped']}"
            f" conflicts_recorded={result['conflicts_recorded']} snapshot_id={result['snapshot_id']}"
        )
    else:
        print("dry-run only; no database changes made (use --apply to import)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
