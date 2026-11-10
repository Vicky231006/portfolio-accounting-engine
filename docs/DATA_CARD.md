# Data Card — AMFI NAVs and Synthetic Portfolio Data

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Status | Draft for M0 review |
| Date | 2026-11-09 |
| Market data | Real AMFI NAV observations obtained through FundLens |
| Account data | Synthetic, deterministic, clearly labelled |
| Related documents | `docs/FUNDLENS_NAV_CONTRACT.md`, `docs/METHODOLOGY.md`, `DECISIONS.md` |

> **Disclosure:** This project uses synthetic investors, accounts and transactions. It uses real public AMFI mutual-fund NAV observations as market inputs. It does not contain real client data, PAN, Aadhaar, brokerage credentials or account information. It is an educational prototype, not investment advice, not a production system and not a regulatory-compliance claim.

---

## 1. Market data source

| Field | Value |
|---|---|
| Provider | Association of Mutual Funds in India (AMFI) |
| Endpoint used by FundLens | `https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx` |
| Query parameters | `frmdt`, `todt`, formatted `DD-Mon-YYYY` |
| Access method | Historical NAV history report, downloaded in date chunks by FundLens |
| FundLens raw storage | `data/raw/amfi/<year>/amfi_nav_<from>_<to>_<sha256[:12]>.txt.gz` |
| FundLens standardised storage | `core.fact_nav` joined to `core.dim_scheme` and `raw.source_file` |
| Retrieval date recorded by FundLens | 2026-11-07 |
| History start | 2006-04-01; earlier requests return an HTML page rather than NAV data |
| Last observation in the inspected latest file | 2026-11-06 |

The project does **not** call AMFI directly as its primary path. It consumes the AMFI observations already sourced by FundLens through the verified contract in `docs/FUNDLENS_NAV_CONTRACT.md`.

### 1.1 Terms of use

FundLens's data card records that AMFI's terms of use permit personal, non-commercial use only and prohibit publishing, transferring or creating derivative works from site content. FundLens therefore does not redistribute NAV data.

This project follows the same rule:

- raw and canonical NAV files are local and git-ignored;
- the repository contains no NAV series or per-scheme data dump;
- published results contain aggregates and explicitly labelled examples;
- dashboard files are run against the user's own local database; data-bearing `.pbix` files are not committed;
- screenshots show aggregates or synthetic examples, not a redistributable NAV dataset.

This is a data-use decision, not legal advice.

---

## 2. FundLens contract used

The full contract is in `docs/FUNDLENS_NAV_CONTRACT.md`. In summary:

- **Scheme identity:** `core.dim_scheme.amfi_code` (stable AMFI scheme code). Names are display data; name similarity is never used to merge schemes.
- **Plan/option:** `plan_type` (`DIRECT`, `REGULAR`, `UNKNOWN`), `option_type` (`GROWTH`, `IDCW`, `UNKNOWN`). This project uses `DIRECT` + `GROWTH` for its primary accounts.
- **Category:** FundLens-normalised category from the AMFI section header.
- **NAV observation:** `core.fact_nav(scheme_id, nav_date, nav NUMERIC(20,6), file_id, loaded_at)`, primary key `(scheme_id, nav_date)`.
- **Provenance:** `raw.source_file(source_url, retrieved_at, from_date, to_date, http_status, file_path, sha256, byte_size, line counts, scope_config_hash)`.
- **Renames:** `core.scheme_name_history` records every observed name; `core.scheme_mapping` holds explicit, evidence-backed relationships and never auto-confirms them.
- **Conflicts:** a later NAV that disagrees with an existing `(scheme_id, nav_date)` is recorded in `core.nav_revision_conflict`; the stored value is not silently replaced.

### 2.1 Canonical export

The preferred input is a local CSV with this schema:

`scheme_code, scheme_name, amc_name, category, plan_type, option_type, isin, nav_date, nav, source_file_id, source_sha256, source_url, retrieved_at, loaded_at, scope_config_hash`

The CSV is accompanied by a manifest containing the contract version, exact query hash, row count, distinct schemes, min/max NAV date, CSV SHA-256, FundLens schema migration list and extraction mode. The query and schema are in `docs/FUNDLENS_NAV_CONTRACT.md`.

---

## 3. Observed coverage and verification

### 3.1 Raw-file verification

| Metric | Observed value |
|---|---:|
| Gzip files present | 86 |
| Distinct date ranges | 85 |
| Data lines parsed (8-field rows) | 38,321,040 |
| In-scope rows in the 11 categories (all plans/options, per file) | 3,916,242 |
| Unique in-scope `(scheme_code, nav_date)` observations | 3,833,130 |
| Direct-Growth rows in those categories (per file) | 798,178 |
| Unique Direct-Growth `(scheme_code, nav_date)` observations | 781,277 |
| First Direct-Growth observation in sampled long-history schemes | 2013-01-02 |
| Last observation in the latest file | 2026-11-06 |

Every filename's 12-hex SHA-256 prefix matched the SHA-256 of the uncompressed content across all 86 files. Counts are from `docs/FUNDLENS_FILE_RECONCILIATION.md` and its `scripts/m0_reconcile_raw_files.py` scan. An earlier draft's Direct-Growth figure of 435,745 is withdrawn; it was not reproduced.

### 3.2 Duplicate range and conflict

The range `2006-06-30 .. 2006-09-27` appears twice with different content hashes. The files have the same total line count (124,427) and the same 8-field data line count (123,328). They differ on three NAV values, all for the out-of-scope IDCW scheme `100793` (Sundaram Banking and PSU Debt Fund Regular Plan - IDCW), on 26-Jul-2006, 18-Aug-2006 and 29-Aug-2006. No Growth-plan row differs.

This is a real AMFI restatement example. The adapter records conflicts rather than overwriting. The 86-file / 85-registered difference is reconciled in `docs/FUNDLENS_FILE_RECONCILIATION.md`: 86 files cover 85 distinct ranges, and the duplicate range is the extra file.

### 3.3 FundLens audited snapshot

FundLens's `RESULTS.md` (audited 2026-11-08) reports:

- 85 registered source files;
- 1,811,703 `core.fact_nav` rows;
- 779 schemes (375 Direct, 404 Regular);
- NAV date range 2006-04-02 to 2026-11-06.

These are prior documented evidence, not a fresh query from this project. The M0 contract review flags the difference from the 86 raw files.

### 3.4 Representative long-history Direct-Growth schemes

Verified examples (full table in `docs/FUNDLENS_NAV_CONTRACT.md`):

| Category | AMFI code | Observed n | First | Last |
|---|---|---:|---|---|
| Large Cap | 119528 | 3,409 | 2013-01-02 | 2026-11-06 |
| Large & Mid Cap | 119436 | 3,409 | 2013-01-02 | 2026-11-06 |
| Mid Cap | 119620 | 3,409 | 2013-01-02 | 2026-11-06 |
| Small Cap | 119556 | 3,406 | 2013-01-07 | 2026-11-06 |
| Flexi Cap | 120564 | 3,409 | 2013-01-02 | 2026-11-06 |
| Focused | 119564 | 3,409 | 2013-01-02 | 2026-11-06 |
| Value | 118481 | 3,419 | 2013-01-02 | 2026-11-06 |
| Contra | 119769 | 3,409 | 2013-01-02 | 2026-11-06 |
| Dividend Yield | 119507 | 3,408 | 2013-01-02 | 2026-11-05 |
| ELSS | 119544 | 3,409 | 2013-01-02 | 2026-11-06 |

Multi Cap examples are shorter: `148921` starts 2021-05-10 (1,357 observations); `152310` starts 2024-01-31 (684 observations).

---

## 4. Data quality rules

| Rule | Behaviour |
|---|---|
| Non-positive or non-finite NAV | Reject the row and record the reason. |
| Missing scheme code or name | Reject the row. |
| Out-of-scope plan/option/category | Exclude from the primary import and count it. |
| Duplicate `(scheme_code, nav_date)` in one file | Reject the duplicate and count it. |
| Conflicting NAV for an existing date | Record in `nav_revision_conflict`; keep the original. |
| Future-dated NAV | Reject. |
| Missing valuation-date NAV | Carry the last NAV forward up to 5 calendar days; flag stale; beyond 5 days fail valuation. |
| No observation for a scheme for the whole period | Exclude the scheme/path with an explicit reason; do not fabricate. |
| Scheme rename | Keep the AMFI code; record name history; never merge by name. |

No silent forward-fill beyond the limit. No fabricated NAV. No use of IDCW amounts, because AMFI NAV files do not supply declared IDCW amounts.

---

## 5. Synthetic data specification

### 5.1 Purpose

Synthetic accounts and transactions provide a safe, reproducible test environment. They are not a claim about real clients, AUM, user behaviour or error rates.

### 5.2 Generator inputs (fixed in config)

| Parameter | Proposed default | Notes |
|---|---|---|
| Seed | `20261109` | Same seed must produce identical logical records. |
| Investor count | 8 | Configurable. |
| Account count | 12 | Some investors have multiple accounts. |
| Account opening dates | 2016-01-01 to 2023-12-31 | Within Direct-Growth NAV coverage. |
| Transaction date range | 2016-01-01 to 2026-10-31 | Latest complete month-end. |
| Transaction-type mix | Contributions, withdrawals, purchases, redemptions, SIP, switch | Documented weights. |
| SIP schedules | Monthly, fixed amount | 1–3 SIPs per account. |
| Opening cash | Zero | Accounts start with zero cash and units. |
| Funding | Explicit `CONTRIBUTION` | No implicit opening balance. |
| Correction frequency | 5–10% of eligible transactions | Generator-controlled, not a real error rate. |
| Backdating delay | 1–30 calendar days | Simulated knowledge time. |
| Amount distribution | Log-normal / fixed bands | Documented bounds; no negative amounts. |
| Simulated clock | UTC | Every transaction and correction carries `recorded_at`. |

### 5.3 Required generated records

- Investor and account master.
- Account status and opening date.
- Cash contributions and withdrawals.
- Purchases (amount-instructed) and redemptions (unit-instructed).
- SIP instalments with contribution and purchase legs.
- Switches with source redemption and target purchase legs.
- Corrections: replace, void, reverse-and-replace.
- Rejected corrections and the reason.
- Simulated report generation events and snapshots.
- A generator seed/config hash and run log.

### 5.4 Determinism

- The generator uses a seeded pseudo-random number generator; no wall-clock or unordered iteration affects logical output.
- Two runs with the same seed, config and NAV snapshot produce identical logical records and canonical hashes.
- The pipeline records seed, config hash, generator version, NAV snapshot ID, row counts and date range.
- The synthetic clock is independent of wall-clock time. Wall-clock time is used only for pipeline audit metadata.

### 5.5 Synthetic labelling

The disclosure appears in:

- `README.md`;
- `RESULTS.md`;
- `docs/DATA_CARD.md` (this document);
- the dashboard footer on every page;
- dashboard screenshots;
- resume wording;
- any exported summary;
- the report payload metadata (for example `"data_class": "synthetic_accounts_real_nav"`).

---

## 6. Known gaps and limitations

1. **History start:** AMFI data starts 2006-04-01; Direct plans start in 2013. Direct-only analysis before 2013 is impossible.
2. **Survivorship bias:** schemes that closed or merged are largely absent from later files; the bias magnitude is unknown.
3. **Current category labels:** AMFI re-labels historical rows with current categories; category membership is not point-in-time.
4. **No holiday calendar:** the project uses NAV availability and a documented stale-NAV limit, not an exchange holiday calendar.
5. **NAV gaps:** missing observations are carried forward up to 5 calendar days and flagged; beyond that, valuation fails.
6. **Restatements:** AMFI can publish a different NAV for the same date; the project records conflicts and does not silently overwrite.
7. **No IDCW:** Growth plans only; IDCW amounts and reinvestment are out of scope.
8. **No fees:** fees and charges are deferred and not modelled.
9. **No real clients:** all accounts, transactions and corrections are synthetic. No AUM, user count or prevalence claim is made.
10. **No regulatory claim:** the project is not GIPS-compliant and does not claim SEBI compliance.
11. **FundLens coupling:** the contract is read-only; the live DB query and file-count reconciliation remain to be executed.

---

## 7. Provenance record required per import

Every import must record:

- contract version and exact query hash;
- CSV SHA-256 and manifest SHA-256;
- source file IDs and SHA-256 values;
- source URLs and retrieval timestamps;
- import timestamp and operator;
- row counts (total, accepted, rejected, duplicate, conflict);
- distinct schemes, min/max NAV date;
- validation outcomes and reasons;
- FundLens schema migration list / version;
- whether the extract came from the DB query or the raw-file fallback.

A report snapshot must store the `nav_snapshot_id` and checksum so a later import cannot silently change a historical report.
