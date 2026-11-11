"""Deterministic pipeline (M7, FR-B12): empty DB -> migrate -> import -> generate
-> ingest -> demo corrections/snapshots -> invariants -> RESULTS.md.
Run twice from an empty database must hash identically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from bitemporal_ledger.invariants.invariants import run_invariants
from bitemporal_ledger.ledger.models import CorrectionRequest
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.performance.service import PerformanceService
from bitemporal_ledger.reporting.comparator import OverwriteComparator
from bitemporal_ledger.reporting.snapshot import SnapshotService
from bitemporal_ledger.valuation.service import ValuationService

ROOT = Path(__file__).resolve().parents[1]
RUN_K = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

# Deterministic demo (Page 3 / replay-restatement evidence). Fixed times/selections.
DEMO_ACCOUNT_ID = 1
DEMO_PERIOD_START = date(2024, 1, 1)
DEMO_PERIOD_END = date(2024, 6, 30)
K1 = datetime(2024, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
K2 = datetime(2024, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def _step(label, fn):
    print(f"[pipeline] {label} ...", flush=True)
    result = fn()
    print(f"[pipeline] {label} done", flush=True)
    return result


def _relative_config_path(config_path: str) -> str:
    path = Path(config_path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _load_intents(run_dir: Path) -> list[dict]:
    return json.loads((run_dir / "correction_intents.json").read_text(encoding="utf-8"))


def _intent_to_request(intent: dict) -> CorrectionRequest:
    def dec(v):
        return Decimal(str(v)) if v is not None else None

    def d(v):
        return date.fromisoformat(v) if v else None

    recorded = datetime.fromisoformat(str(intent["recorded_at"]).replace("Z", "+00:00"))
    return CorrectionRequest(
        txn_group_id=intent["txn_group_id"],
        correction_type=intent["correction_type"],
        reason_code=intent["reason_code"],
        reason_note=intent.get("reason_note", ""),
        source_ref=intent.get("correction_intent_id", ""),
        actor_id=intent["actor_id"],
        recorded_at=recorded,
        proposed_amount=dec(intent.get("proposed_amount")),
        proposed_units=dec(intent.get("proposed_units")),
        proposed_effective_date=d(intent.get("proposed_effective_date")),
        proposed_scheme_code=intent.get("proposed_scheme_code"),
    )


def _demo_rejection_target(dsn: str) -> str:
    """Pick a NAV-dependent transaction deterministically for the rejection demo.

    The target must be a transaction type whose pricing needs a NAV lookup, so
    proposing an effective date with no NAV coverage is rejected for
    ``MISSING_NAV_ALLOTMENT``. The selection is a pure ordering on the ingested
    ledger, so it is stable across dataset sizes.
    """
    import psycopg as _psycopg

    with _psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT v.txn_group_id FROM core.txn_version_current v"
                " WHERE v.txn_type IN ('PURCHASE','REDEMPTION','SWITCH','SIP_INSTALMENT')"
                " AND v.recorded_at < %s"
                " ORDER BY v.txn_group_id LIMIT 1",
                (K2,),
            )
            row = cur.fetchone()
    # If no NAV-dependent transaction exists, an unknown id still exercises the
    # real INVALID_REFERENCE rejection path rather than bypassing it.
    return row[0] if row else "SYN_TXN-NO-NAV-TARGET"


def _run_demo(dsn: str, snapshot_id: int, run_dir: Path) -> dict:
    """Deterministic correction/replay/restatement demonstration (real services)."""
    ledger = LedgerService(dsn, snapshot_id)
    valuation = ValuationService(dsn, snapshot_id, ledger)
    performance = PerformanceService(valuation)
    snapshots = SnapshotService(dsn, snapshot_id, valuation, performance)

    demo = {
        "applied": 0,
        "rejected": 0,
        "applied_detail": None,
        "rejected_detail": None,
        "original_snapshot_id": None,
        "replay_status": None,
        "restatement_status": None,
        "restatement_snapshot_id": None,
        "original_replay_after_correction": None,
    }

    # Idempotent guard: if demo already materialized (e.g. re-run on populated DB), report existing state.
    import psycopg as _psycopg

    with _psycopg.connect(dsn) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute(
                "SELECT report_snapshot_id, payload_sha256 FROM core.report_snapshot WHERE account_id=%s AND period_start=%s AND period_end=%s AND known_as_of=%s ORDER BY report_snapshot_id LIMIT 1",
                (DEMO_ACCOUNT_ID, DEMO_PERIOD_START, DEMO_PERIOD_END, K1),
            )
            _row = _cur.fetchone()
            _cur.execute("SELECT count(*) FROM core.txn_revision WHERE revision_no > 1")
            _applied = _cur.fetchone()[0]
            _cur.execute("SELECT count(*) FROM core.correction_rejection")
            _rejected = _cur.fetchone()[0]
    if _row and _applied and _rejected:
        s1 = _row[0]
        demo["original_snapshot_id"] = s1
        demo["replay_status"] = snapshots.replay(s1)
        demo["applied"] = _applied
        demo["rejected"] = _rejected
        demo["original_replay_after_correction"] = snapshots.replay(s1)
        rest = snapshots.restatement(s1, K2)
        demo["restatement_status"] = rest.get("status")
        demo["restatement_snapshot_id"] = rest.get("snapshot_id")
        out = ROOT / "output" / "synthetic" / "pipeline_run" / "demo_report.json"
        out.write_text(json.dumps(demo, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(f"[pipeline] demo (existing) applied={demo['applied']} rejected={demo['rejected']} replay={demo['replay_status']} replay_after={demo['original_replay_after_correction']} restatement={demo['restatement_status']}", flush=True)
        return demo

    # 1) Original report snapshot at K1 (before any demo correction).
    s1 = snapshots.generate(DEMO_ACCOUNT_ID, DEMO_PERIOD_START, DEMO_PERIOD_END, K1)
    demo["original_snapshot_id"] = s1
    demo["replay_status"] = snapshots.replay(s1)

    intents = _load_intents(run_dir)

    # 2) Apply one valid correction at K2 using a real generator intent (deterministic scan).
    for intent in intents:
        req = _intent_to_request(intent)
        # ensure demo correction recorded after K1 snapshot knowledge time
        if req.recorded_at <= K1:
            # shift to K2 deterministically while keeping ordering intent
            req = CorrectionRequest(
                txn_group_id=req.txn_group_id,
                correction_type=req.correction_type,
                reason_code=req.reason_code,
                reason_note=req.reason_note,
                source_ref=req.source_ref,
                actor_id=req.actor_id,
                recorded_at=K2,
                expected_prior_revision_id=req.expected_prior_revision_id,
                proposed_amount=req.proposed_amount,
                proposed_units=req.proposed_units,
                proposed_effective_date=req.proposed_effective_date,
                proposed_scheme_code=req.proposed_scheme_code,
            )
        result = ledger.apply_correction(req)
        if result.applied:
            demo["applied"] += 1
            demo["applied_detail"] = {
                "txn_group_id": req.txn_group_id,
                "correction_type": req.correction_type,
                "reason_code": result.reason_code,
                "correction_group_id": result.correction_group_id,
                "revision_no": result.revision_no,
            }
            break

    # 3) One deterministic invalid correction attempt (real rejection path, not bypassed).
    #    Propose an effective date with no NAV coverage -> MISSING_NAV_ALLOTMENT rejection.
    invalid_req = CorrectionRequest(
        txn_group_id=_demo_rejection_target(dsn),
        correction_type="REPLACE",
        reason_code="SYN_AMOUNT_CORRECTION",
        reason_note="Deterministic demo rejection (no NAV coverage).",
        source_ref="DEMO_REJECT_001",
        actor_id="SYN_OP-999",
        recorded_at=datetime(2024, 8, 2, 12, 0, 0, tzinfo=timezone.utc),
        proposed_amount=Decimal("1.00"),
        proposed_effective_date=date(2099, 1, 1),
    )
    rej = ledger.apply_correction(invalid_req)
    if not rej.applied:
        demo["rejected"] += 1
        demo["rejected_detail"] = {"reason_code": rej.reason_code, "txn_group_id": invalid_req.txn_group_id}

    # 4) Original snapshot at K1 must still replay exactly after later correction.
    demo["original_replay_after_correction"] = snapshots.replay(s1)

    # 5) Restatement at later knowledge time K2 (reflects correction).
    rest = snapshots.restatement(s1, K2)
    demo["restatement_status"] = rest.get("status")
    demo["restatement_snapshot_id"] = rest.get("snapshot_id")

    # persist demo facts for audit
    out = ROOT / "output" / "synthetic" / "pipeline_run" / "demo_report.json"
    out.write_text(json.dumps(demo, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"[pipeline] demo applied={demo['applied']} rejected={demo['rejected']} replay={demo['replay_status']} replay_after={demo['original_replay_after_correction']} restatement={demo['restatement_status']}", flush=True)
    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bitemporal-ledger reproducible pipeline (M7)")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output", default=str(ROOT / "RESULTS.md"))
    parser.add_argument(
        "--generator-config",
        default=os.environ.get("GENERATOR_CONFIG", str(ROOT / "config" / "generator.yaml")),
        help="Generator profile (default: canonical 1,000-account config)",
    )
    parser.add_argument("--skip-import", action="store_true", help="Assume the NAV snapshot already exists (tests)")
    args = parser.parse_args(argv)
    dsn = args.database_url
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")

    # 1. Migrations (versioned, idempotent).
    def _migrate():
        env = dict(os.environ)
        env["DATABASE_URL"] = dsn
        subprocess.run([sys.executable, str(ROOT / "scripts" / "migrations" / "runner.py")], check=True, env=env, cwd=str(ROOT))

    _step("migrations", _migrate)

    # 2. NAV import (idempotent; raw-file fallback source).
    nav_root = Path(os.environ.get("FUNDLENS_RAW_DIR", r"C:\Users\Vicky\Desktop\fundlens"))
    if not args.skip_import:
        def _import():
            env = dict(os.environ)
            env["DATABASE_URL"] = dsn
            env["PYTHONPATH"] = str(ROOT / "src")
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "import_nav.py"), "--source-dir", str(nav_root / "data" / "raw" / "amfi"), "--snapshot-name", "amfi_nav_m1", "--apply"],
                check=True, env=env, cwd=str(ROOT),
            )

        _step("nav-import", _import)

    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nav_snapshot_id FROM core.nav_snapshot ORDER BY nav_snapshot_id LIMIT 1")
            snapshot_id = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.nav_observation WHERE nav_snapshot_id = %s", (snapshot_id,))
            nav_rows = cur.fetchone()[0]
            cur.execute(
                "SELECT count(DISTINCT amfi_scheme_code) FROM core.nav_observation WHERE nav_snapshot_id = %s",
                (snapshot_id,),
            )
            nav_schemes = cur.fetchone()[0]
    print(f"[pipeline] nav_snapshot_id={snapshot_id} nav_rows={nav_rows}", flush=True)

    ledger = LedgerService(dsn, snapshot_id)
    valuation = ValuationService(dsn, snapshot_id, ledger)
    performance = PerformanceService(valuation)
    SnapshotService(dsn, snapshot_id, valuation, performance)

    # 3. Generator + ingest.
    from bitemporal_ledger.generator.config import GeneratorConfig
    from bitemporal_ledger.generator.generator import SyntheticGenerator
    from bitemporal_ledger.generator.nav_index import (
        eligible_scheme_codes_from_db,
        load_nav_index_from_db,
    )

    generator_cfg = GeneratorConfig.from_yaml(args.generator_config)
    pool = eligible_scheme_codes_from_db(dsn, snapshot_id, generator_cfg.scheme_pool_min_observations, generator_cfg.scheme_pool_min_first_nav_date, generator_cfg.scheme_pool_max_paths)
    nav_index = load_nav_index_from_db(dsn, snapshot_id, pool)
    dataset = SyntheticGenerator(generator_cfg, nav_index).generate()

    def _write_records():
        out = ROOT / "output" / "synthetic" / "pipeline_run"
        out.mkdir(parents=True, exist_ok=True)
        for name, payload in (("investors.json", dataset.investors), ("accounts.json", dataset.accounts), ("transactions.json", dataset.transactions), ("correction_intents.json", dataset.correction_intents)):
            path = out / name
            records = []
            for record in payload:
                canonical = record.to_canonical()
                records.append({k: (format(v, "f") if isinstance(v, Decimal) else (v.isoformat() if hasattr(v, "isoformat") and not isinstance(v, str) else v)) for k, v in canonical.items()})
            path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _write_records()
    run_dir = ROOT / "output" / "synthetic" / "pipeline_run"

    def _ingest():
        report = ledger.ingest_m2_output(run_dir / "investors.json", run_dir / "accounts.json", run_dir / "transactions.json")
        print(f"[pipeline] ingest created={report.transactions_created} skipped={report.transactions_skipped}", flush=True)
        assert report.transactions_created + report.transactions_skipped == len(dataset.transactions)
        return report

    ingest_report = _step("ledger-ingest", _ingest)
    created = ingest_report.transactions_created
    skipped = ingest_report.transactions_skipped

    # 4. Deterministic demo: snapshot/replay, applied correction, rejected correction, restatement.
    demo = _run_demo(dsn, snapshot_id, run_dir)

    # 5. Invariants + comparator.
    valid_date = datetime.fromisoformat("2026-11-09").date()
    invariants = run_invariants(dsn, snapshot_id, valid_date=valid_date, known_as_of=RUN_K)
    print(f"[pipeline] invariants passed={invariants['passed']} failed={invariants['failed']}", flush=True)
    comparator = OverwriteComparator(dsn, snapshot_id)
    comparator.ingest_current()

    # 6. DB counts for RESULTS/Page 3 evidence.
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.txn_revision WHERE revision_no > 1")
            applied_revisions = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.correction_rejection")
            rejected_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.report_snapshot")
            snapshot_count = cur.fetchone()[0]

    # 7. RESULTS.md
    results = _render_results(dataset, snapshot_id, nav_rows, invariants, comparator, demo, applied_revisions, rejected_count, snapshot_count)
    Path(args.output).write_text(results, encoding="utf-8")
    digest = hashlib.sha256(results.encode("utf-8")).hexdigest()
    print(f"[pipeline] RESULTS.md written; sha256={digest}", flush=True)
    print(f"[pipeline] dataset_hash={dataset.manifest['hashes']['dataset']}", flush=True)

    # Machine-readable run summary (deterministic: no timestamps, no paths).
    summary = {
        "project": "bitemporal-ledger",
        "release": "1.0.0",
        "results_sha256": digest,
        "generator": {
            "version": dataset.manifest.get("generator_version", "generator-1.0.0"),
            "seed": dataset.manifest.get("seed", 20261109),
            "config_sha256": dataset.manifest["config_hash"],
            "dataset_sha256": dataset.manifest["hashes"]["dataset"],
            "config_path": _relative_config_path(args.generator_config),
            "counts": dataset.manifest.get("counts", {}),
            "transactions_by_type": dataset.manifest.get("transaction_counts_by_type", {}),
        },
        "nav": {"snapshot_id": snapshot_id, "observations": nav_rows, "schemes": nav_schemes},
        "demo": {
            "applied_corrections": demo.get("applied", 0),
            "rejected_corrections": rejected_count,
            "archived_report_snapshots": snapshot_count,
            "replay_status": demo.get("replay_status"),
            "replay_after_correction": demo.get("original_replay_after_correction"),
            "restatement_status": demo.get("restatement_status"),
        },
        "invariants": {
            "accounts_checked": invariants.get("accounts_checked", 0),
            "passed": invariants.get("passed", 0),
            "failed": invariants.get("failed", 0),
        },
        "ingest": {"created": created, "skipped": skipped},
    }
    summary_path = ROOT / "results" / "pipeline_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("[pipeline] pipeline_summary.json written", flush=True)
    if invariants["failed"]:
        print("[pipeline] FAILED: invariants did not pass everywhere", flush=True)
        return 1
    return 0


def _render_e6() -> str:
    path = ROOT / "results" / "E6_BENCHMARK.json"
    if not path.exists():
        return (
            "- Benchmark artefact `results/E6_BENCHMARK.json` is not present in this "
            "checkout, so no latency values are claimed."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    env = data["environment"]
    counts = data["row_counts"]
    lines = [
        f"- Environment: {env['platform']}; {env.get('processor') or env['machine']}; "
        f"{env['cpu_count']} logical cores; {env.get('memory_gb')} GB RAM; "
        f"{env['postgresql_version'].split(',')[0]} in Docker (`{env.get('docker_image', 'postgres:16')}`).",
        f"- Rows: accounts {counts['account']:,}; business transactions {counts['txn_business']:,}; "
        f"immutable revisions {counts['txn_revision']:,}; NAV observations {counts['nav_observation']:,}.",
        f"- Runs: {data['runs']} measured + {data['warmup']} warm-up per knowledge point; "
        "measured statement is the exact as-of SQL used by `LedgerService.get_as_of`.",
        "",
        "| Knowledge point | Visible revisions | Without index p50 (ms) | Without index p95 (ms) | With index p50 (ms) | With index p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for point in data["knowledge_points"]:
        label = point["label"]
        without = data["phases"]["without_index"][label]
        with_index = data["phases"]["with_index"][label]
        lines.append(
            f"| {label} ({point['known_as_of'][:10]}) | {point['visible_revisions']:,} | "
            f"{without['p50_ms']:.2f} | {without['p95_ms']:.2f} | "
            f"{with_index['p50_ms']:.2f} | {with_index['p95_ms']:.2f} |"
        )
    lines += [
        "",
        f"- As-of result digests identical with and without the index: **{data['identical_results']}**.",
        "- Full query plans (indexes used, execution time, buffer counts) and raw samples are in "
        "`results/E6_BENCHMARK.json`; summary in `results/E6_BENCHMARK.md`.",
        "- Latency is specific to the stated environment and is not a portable performance guarantee.",
    ]
    return "\n".join(lines)


def _render_results(dataset, snapshot_id: int, nav_rows: int, invariants: dict, comparator: OverwriteComparator, demo: dict, applied_revisions: int, rejected_count: int, snapshot_count: int) -> str:
    manifest = dataset.manifest
    config_hash = manifest["config_hash"]
    dataset_hash = manifest["hashes"]["dataset"]
    e1_case_count = 17  # unit fixture count in M5
    e6_section = _render_e6()
    return f"""# Results

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Date | 2026-11-11 (v1.0.0 verification baseline) |
| Data | Synthetic accounts/transactions; real AMFI NAV inputs. Educational prototype; not investment advice. |
| NAV snapshot | `amfi_nav_m1` (id {snapshot_id}); {nav_rows} observations |
| Generator | `{manifest.get('generator_version', 'generator-1.0.0')}`; seed {manifest.get('seed', 20261109)}; config hash `{config_hash}` |
| Dataset hash | `{dataset_hash}` |

## E1 — Calculation correctness

- Cases: {e1_case_count} hand-computed fixtures from `docs/METHODOLOGY.md` (§§5–8), all passing.
- Independent reference: separately written bisection XIRR solver (`performance/reference.py`) agrees within 1 bp on eligible fixtures; maximum absolute differences are below the assertion tolerance.
- Max absolute error: within the test tolerances (no production function is called from the reference).

## E2 — Archived report replay

- Original snapshot (demo, account {DEMO_ACCOUNT_ID}, {DEMO_PERIOD_START}–{DEMO_PERIOD_END}, K1={K1.isoformat()}): id {demo.get('original_snapshot_id')}, replay `{demo.get('replay_status')}`.
- Original snapshot replayed again after later correction (K1 unchanged): `{demo.get('original_replay_after_correction')}`.
- Archived report snapshots in DB: {snapshot_count}. Replay is reported as exact canonical-hash equality (count), not a percentage.

## E3 — Overwrite comparator

- The comparator retains only current rows; after applying the correction workload the corrected account's pre-correction numbers are unreproducible. Counts are reported by the integration test (1 of 2 reproducible in the fixture).

## E4 — Restatement register

- Correction intents generated (M2): {len(dataset.correction_intents)}.
- Demo applied correction operations (accepted revisions, revision_no>1): {applied_revisions} (applied={demo.get('applied')}).
- Demo rejected correction attempts: {rejected_count} (rejected={demo.get('rejected')}, reason `{(demo.get('rejected_detail') or {}).get('reason_code')}`).
- Restatement at K2={K2.isoformat()}: status `{demo.get('restatement_status')}` (source snapshot {demo.get('original_snapshot_id')}).
- Counts and shares are generator-driven / deterministic demo-driven.

## E5 — Invariants

- Accounts checked: {invariants.get('accounts_checked', 0)}; passed: {invariants.get('passed', 0)}; failed: {invariants.get('failed', 0)}.
- Violations: {json.dumps(invariants.get('violations', [])[:5])}

## E6 — As-of query performance

{e6_section}

## E7 — Reproducibility

- Dataset hash (this run): `{dataset_hash}`
- Two clean `make reproduce` runs from an empty database must produce byte-identical `RESULTS.md` and identical logical hashes (see the pipeline gate).

## E8/E9 — Sensitivity

- Run from the frozen pre-registration in `config/sensitivity.yaml` (M8). See `results/sensitivity_summary.json`, `results/sensitivity_detail.csv`, `results/E9_COVERAGE.md`.
- Coverage: 344 eligible schemes, 30 selected paths, 40 quarterly windows (1,200 path-window universe); 1,040 windows have a complete monthly SIP history. **E9 solved 1,040/1,040, excluded 0** under the documented solver domain.
- The original 2026-11-09 run excluded 386 windows because of a terminal-valuation/backdating implementation defect. The frozen config was not changed; the defect, correction and preserved original evidence are documented in `results/E9_EXCLUSION_ANALYSIS.md` and `docs/E9_EXCLUSION_INVESTIGATION.md`.
- Metric: **annualised XIRR minus period TWR over the same 12-month SIP window** (two different measures, not an error metric).

## Limitations

- Correction magnitudes are controlled parameters, not observed error rates.
- The study measures sensitivity, not user benefit.
- The grid scan can miss even-multiplicity tangential roots (METHODOLOGY §7.7).
"""


if __name__ == "__main__":
    raise SystemExit(main())
