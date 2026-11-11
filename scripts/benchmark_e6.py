"""E6 — as-of query latency benchmark (PRD §9 E6, FR-B12).

Measures the exact as-of SQL used by ``LedgerService.get_as_of`` at four
knowledge-time points, with and without the dedicated recorded-at index
(migration 008). Reports p50 / p95 wall-clock latency, row counts, the
PostgreSQL query plan and the runtime environment.

The ``without`` phase drops the index and the ``with`` phase recreates it.
This is DDL on the target database, so it requires ``--allow-index-ddl`` and
must be pointed at a disposable/benchmark database, never production.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql://postgres:<pw>@127.0.0.1:5434/bitemporal_ledger_v1a"
    python scripts/benchmark_e6.py --allow-index-ddl --runs 30

Outputs (default):
    results/E6_BENCHMARK.json   machine-readable raw samples + environment
    results/E6_BENCHMARK.md     human-readable summary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
INDEX_NAME = "core.ix_txn_revision_recorded_at"
INDEX_DEFINITION = (
    "CREATE INDEX ix_txn_revision_recorded_at ON core.txn_revision (recorded_at)"
)

# Exact statement used by LedgerService.get_as_of (M3/M4).
AS_OF_SQL = """
SELECT DISTINCT ON (r.txn_group_id) r.txn_group_id, r.txn_revision_id, r.revision_no, r.revision_kind, r.revision_status,
       r.txn_type, b.account_id, r.instruction_date, r.effective_date, r.allotment_date, r.source_nav_date,
       r.target_allotment_date, r.posting_sequence, r.scheme_code, r.source_scheme_code, r.target_scheme_code,
       r.amount_instructed, r.units_instructed, r.recorded_at
FROM core.txn_revision r JOIN core.txn_business b ON b.txn_group_id = r.txn_group_id
WHERE r.recorded_at <= %s
ORDER BY r.txn_group_id, r.revision_no DESC
"""


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _memory_gb() -> float | None:
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / (1024**3), 1)
    except Exception:
        pass
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / (1024**2), 1)
    except Exception:
        pass
    return None


def _environment(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        pg_version = cur.fetchone()[0]
        settings = {}
        for name in (
            "server_version",
            "shared_buffers",
            "work_mem",
            "effective_cache_size",
            "maintenance_work_mem",
            "max_parallel_workers_per_gather",
            "random_page_cost",
        ):
            cur.execute("SHOW " + name)
            settings[name] = cur.fetchone()[0]
    return {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "memory_gb": _memory_gb(),
        "postgresql_version": pg_version,
        "server_settings": settings,
        "database_in_docker": os.environ.get("E6_DATABASE_IN_DOCKER", "unknown"),
        "docker_image": os.environ.get("E6_DOCKER_IMAGE", "postgres:16"),
    }


def _row_counts(conn) -> dict:
    counts = {}
    with conn.cursor() as cur:
        for table in (
            "core.investor",
            "core.account",
            "core.txn_business",
            "core.txn_revision",
            "core.correction_group",
            "core.report_snapshot",
            "core.nav_observation",
        ):
            cur.execute("SELECT count(*) FROM " + table)
            counts[table.split(".")[1]] = cur.fetchone()[0]
    return counts


def _knowledge_points(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_timestamp(percentile_cont(0.25) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM recorded_at))::float8) AS p25,"
            "       to_timestamp(percentile_cont(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM recorded_at))::float8) AS p50,"
            "       to_timestamp(percentile_cont(0.75) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM recorded_at))::float8) AS p75,"
            "       max(recorded_at) AS recorded_at_max"
            " FROM core.txn_revision"
        )
        row = cur.fetchone()
        points = []
        for label, value in zip(("p25", "p50", "p75", "max"), row):
            cur.execute(
                "SELECT count(*) FROM core.txn_revision WHERE recorded_at <= %s",
                (value,),
            )
            visible = cur.fetchone()[0]
            points.append(
                {
                    "label": label,
                    "known_as_of": value.isoformat(),
                    "visible_revisions": visible,
                }
            )
    return points


def _visible_digest(conn, known_as_of) -> str:
    with conn.cursor() as cur:
        cur.execute(AS_OF_SQL, (known_as_of,))
        rows = cur.fetchall()
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row[0]}|{row[1]}|{row[2]}|".encode("utf-8"))
    return digest.hexdigest()


def _measure(conn, known_as_of, runs: int, warmup: int) -> list[float]:
    timings = []
    with conn.cursor() as cur:
        for _ in range(warmup):
            cur.execute(AS_OF_SQL, (known_as_of,))
            cur.fetchall()
        for _ in range(runs):
            start = time.perf_counter()
            cur.execute(AS_OF_SQL, (known_as_of,))
            cur.fetchall()
            timings.append((time.perf_counter() - start) * 1000.0)
    return timings


def _plan(conn, known_as_of) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + AS_OF_SQL,
            (known_as_of,),
        )
        payload = cur.fetchone()[0]
    plan = payload[0]
    indexes: list[str] = []
    nodes: list[dict] = []

    def walk(node: dict) -> None:
        nodes.append(
            {
                "node_type": node.get("Node Type"),
                "index_name": node.get("Index Name"),
                "actual_total_ms": node.get("Actual Total Time"),
                "shared_hit_blocks": node.get("Shared Hit Blocks"),
                "shared_read_blocks": node.get("Shared Read Blocks"),
            }
        )
        if node.get("Index Name"):
            indexes.append(node["Index Name"])
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return {
        "execution_ms": plan.get("Execution Time"),
        "planning_ms": plan.get("Planning Time"),
        "indexes_used": indexes,
        "nodes": nodes,
    }


def _index_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (INDEX_NAME,))
        return cur.fetchone()[0] is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E6 as-of query benchmark")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL DSN (use a disposable database)",
    )
    parser.add_argument("--runs", type=int, default=30, help="Measured runs per point")
    parser.add_argument("--warmup", type=int, default=3, help="Warm-up runs per point")
    parser.add_argument(
        "--allow-index-ddl",
        action="store_true",
        help="Permit DROP/CREATE of the benchmark index (disposable DB only)",
    )
    parser.add_argument("--json-output", default=str(ROOT / "results" / "E6_BENCHMARK.json"))
    parser.add_argument("--md-output", default=str(ROOT / "results" / "E6_BENCHMARK.md"))
    args = parser.parse_args(argv)

    if not args.database_url:
        raise RuntimeError("DATABASE_URL is not set (or pass --database-url)")
    if not args.allow_index_ddl:
        print(
            "Refusing to run: this benchmark drops and recreates an index. "
            "Re-run with --allow-index-ddl against a disposable database.",
            file=sys.stderr,
        )
        return 2

    report: dict = {"metric": "as-of query wall-clock latency (ms)", "phases": {}}
    with psycopg.connect(args.database_url) as conn:
        conn.autocommit = True
        report["environment"] = _environment(conn)
        report["row_counts"] = _row_counts(conn)
        report["runs"] = args.runs
        report["warmup"] = args.warmup
        points = _knowledge_points(conn)
        report["knowledge_points"] = points

        digests: dict[str, dict[str, str]] = {}
        for phase in ("without_index", "with_index"):
            if phase == "without_index":
                with conn.cursor() as cur:
                    cur.execute("DROP INDEX IF EXISTS " + INDEX_NAME)
                    cur.execute("ANALYZE core.txn_revision")
            else:
                with conn.cursor() as cur:
                    cur.execute(INDEX_DEFINITION)
                    cur.execute("ANALYZE core.txn_revision")
            report["phases"][phase] = {}
            for point in points:
                known_as_of = point["known_as_of"]
                timings = _measure(conn, known_as_of, args.runs, args.warmup)
                plan = _plan(conn, known_as_of)
                digest = _visible_digest(conn, known_as_of)
                digests.setdefault(point["label"], {})[phase] = digest
                report["phases"][phase][point["label"]] = {
                    "known_as_of": known_as_of,
                    "visible_revisions": point["visible_revisions"],
                    "runs": len(timings),
                    "min_ms": round(min(timings), 3),
                    "p50_ms": round(_percentile(timings, 50), 3),
                    "p95_ms": round(_percentile(timings, 95), 3),
                    "max_ms": round(max(timings), 3),
                    "mean_ms": round(statistics.fmean(timings), 3),
                    "timings_ms": [round(value, 3) for value in timings],
                    "plan": plan,
                }

        # Prove the index does not change the as-of result.
        mismatches = [
            label
            for label, phases in digests.items()
            if phases.get("without_index") != phases.get("with_index")
        ]
        report["identical_results"] = not mismatches
        report["result_digests"] = digests

        # Leave the database as the migration defines it.
        with conn.cursor() as cur:
            cur.execute("CREATE INDEX IF NOT EXISTS ix_txn_revision_recorded_at ON core.txn_revision (recorded_at)")
            cur.execute("ANALYZE core.txn_revision")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    env = report["environment"]
    lines = [
        "# E6 — As-of Query Benchmark",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Measured at (UTC) | {env['measured_at_utc']} |",
        f"| PostgreSQL | {env['postgresql_version'].split(',')[0]} |",
        f"| Python | {env['python']} |",
        f"| Platform | {env['platform']} |",
        f"| CPU | {env.get('processor') or env['machine']} ({env['cpu_count']} logical cores) |",
        f"| Memory | {env.get('memory_gb')} GB |",
        f"| Database | {env['database_in_docker']}; image `{env['docker_image']}` |",
        f"| Rows | accounts {report['row_counts']['account']:,}; transactions {report['row_counts']['txn_business']:,}; revisions {report['row_counts']['txn_revision']:,}; NAV observations {report['row_counts']['nav_observation']:,} |",
        f"| Runs | {args.runs} measured + {args.warmup} warm-up per point |",
        "",
        "The measured statement is the exact as-of SQL used by "
        "`LedgerService.get_as_of` (visible revisions at knowledge time `K`).",
        "",
        "## Latency (milliseconds)",
        "",
        "| Knowledge point | Visible revisions | Without index p50 | Without index p95 | With index p50 | With index p95 | Speed-up p50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for point in points:
        label = point["label"]
        without = report["phases"]["without_index"][label]
        with_index = report["phases"]["with_index"][label]
        speedup = (
            f"{without['p50_ms'] / with_index['p50_ms']:.2f}x"
            if with_index["p50_ms"]
            else "n/a"
        )
        lines.append(
            f"| {label} ({point['known_as_of'][:10]}) | {point['visible_revisions']:,} | "
            f"{without['p50_ms']:.2f} | {without['p95_ms']:.2f} | "
            f"{with_index['p50_ms']:.2f} | {with_index['p95_ms']:.2f} | {speedup} |"
        )
    lines += [
        "",
        "## Query plans",
        "",
        "| Knowledge point | Phase | Indexes used | Execution ms |",
        "|---|---|---|---:|",
    ]
    for point in points:
        label = point["label"]
        for phase in ("without_index", "with_index"):
            item = report["phases"][phase][label]
            indexes = ", ".join(item["plan"]["indexes_used"]) or "(seq scan only)"
            lines.append(
                f"| {label} | {phase.replace('_', ' ')} | {indexes} | "
                f"{item['plan']['execution_ms']:.2f} |"
            )
    lines += [
        "",
        f"Result digests identical with and without the index: **{report['identical_results']}**.",
        "",
        "## Interpretation limits",
        "",
        "- Latency is hardware-, cache- and PostgreSQL-configuration-specific. These numbers "
        "describe the environment above and are not a portable performance guarantee.",
        "- The benchmark runs the query directly against PostgreSQL; it does not include "
        "Python object construction for every column of `get_as_of`.",
        "- The database was local (containerised PostgreSQL 16); network latency is loopback.",
        "",
        "## Reproduce",
        "",
        "```",
        "python scripts/benchmark_e6.py --allow-index-ddl --runs 30",
        "```",
        "",
    ]
    md_path = Path(args.md_output)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    for point in points:
        label = point["label"]
        without = report["phases"]["without_index"][label]
        with_index = report["phases"]["with_index"][label]
        print(
            f"{label}: without p50={without['p50_ms']:.2f} p95={without['p95_ms']:.2f} | "
            f"with p50={with_index['p50_ms']:.2f} p95={with_index['p95_ms']:.2f}"
        )
    print(f"identical_results={report['identical_results']}")
    return 0 if report["identical_results"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
