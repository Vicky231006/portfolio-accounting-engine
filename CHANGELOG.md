# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-11

First complete release of the **Portfolio Accounting & Performance Engine**.

### Dataset and scale

- Canonical synthetic dataset scaled from 12 to **1,000 accounts** (600
  investors) with **209,937 transactions** and **14,926 correction intents**;
  seed `20261109`, dataset SHA-256
  `833f7f5703c1bbbd8142f0db5c11945b97bf2f844307c9a59887b886b62a2f8a`.
- Added `config/generator.dev.yaml` (12-account development profile) so quick
  local runs remain fast; `config/generator.yaml` is the canonical profile.
- Ledger ingestion rewritten to validate batches up front and write the
  immutable revisions and rebuildable projections with bulk operations instead
  of per-row round-trips.
- NAV import rewritten to bulk `COPY` into a transaction-local staging table
  before an idempotent insert, and no longer scans every source file twice.

### E9 sensitivity correction

- Fixed four implementation defects in the sensitivity helper: terminal
  valuation now uses the last NAV on or before the 12-month window end;
  backdated instalments roll to the next available NAV instead of disappearing;
  the XIRR solver uses the documented production domain
  `(-0.999999, 1000)`; and SIP TWR chain-links NAV subperiod returns.
- E9 now solves **1,040 of 1,040** eligible windows with **0 exclusions**
  (previously 654 solved / 386 excluded). The frozen study configuration and
  metric definition are unchanged.
- Original evidence preserved byte-for-byte in
  `results/archive/e9_v1_frozen/`; investigation recorded in
  `docs/E9_EXCLUSION_INVESTIGATION.md` and `results/E9_EXCLUSION_ANALYSIS.*`.

### E6 query performance

- Added migration `008_e6_perf_index.sql` (`ix_txn_revision_recorded_at`).
- Added `scripts/benchmark_e6.py`, which measures the exact as-of query p50/p95
  with and without the index, records query plans, row counts and the runtime
  environment, verifies identical results between phases, and writes
  machine-readable `results/E6_BENCHMARK.json`.

### Verification and tooling

- Added `scripts/run_sensitivity.py` (refuses to overwrite evidence without
  `--force`) and `scripts/analyze_e9_exclusions.py`.
- `scripts/reproduce.py` accepts `--generator-config` / `GENERATOR_CONFIG`,
  writes deterministic `results/pipeline_summary.json`, and reports measured E6
  results when the benchmark artefact is present.
- Full release verification executed: unit/property/integration tests, Ruff,
  migration checksum/tamper test, NAV re-import idempotency, two clean
  reproduction runs with matching hashes, replay/restatement demonstration and
  pipeline invariants.
- Package version raised to `1.0.0`.

### Documentation

- Rewrote README around the business problem, the v1.0.0 dataset and the
  verified results; added release report, release notes and a dashboard
  screenshot showcase.
- Removed RC positioning and stale instructions; removed the internal agent
  prompt from version control.
- Documented that Power BI Desktop interaction validation is manual in this
  environment and that GitHub Actions execution is confirmed from the Actions
  UI, not locally.

### Known limitations

- Power BI `.pbix` is not committed (data-bearing binary); the PBIP project is
  committed and Power BI Desktop refresh/interaction validation remains a
  manual step.
- GitHub Actions workflow is configured; remote run status must be checked in
  the Actions UI.
- Latency figures describe the documented environment only.
- No fees, taxes, IDCW cash events, multi-currency, equities, bonds or
  derivatives.
