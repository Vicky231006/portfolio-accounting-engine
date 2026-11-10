# FundLens NAV Data Contract

| Field | Value |
|---|---|
| Status | Verified at schema and source-file level; **approved by Vicky 2026-11-09 under Option A** (verified raw-file fallback); FundLens database not queried |
| Date | 2026-11-09 |
| Source project | FundLens (`C:\Users\Vicky\Desktop\fundlens`), read-only |
| Consumer | `bitemporal-ledger` NAV adapter |
| Authoritative source | PRD v2.0 sections 5.1, 5.3 and 9; prompt sections 2.2–2.3 |

This document records what was actually inspected in FundLens and defines the smallest stable contract needed by this project. It does not invent table names, columns, export commands or coverage.

---

## 1. Permission boundary observed

FundLens was inspected **read-only**:

- No FundLens file was created, modified, moved or deleted.
- No FundLens migration or ingestion command was run.
- No FundLens database was modified.
- No FundLens secret or `.env` content was read or copied.
- No external database query was assumed to be authorised merely because the repository is visible.

At the time of inspection the Docker daemon was not running (`docker ps` failed with a missing Docker Desktop named pipe). More importantly, Vicky selected **Option A** on 2026-11-09: use the verified raw-file fallback and **do not query the FundLens PostgreSQL database or access its running database volumes**. The contract below is therefore verified from:

1. the FundLens SQL migration definitions;
2. the FundLens ingestion parser and scope config;
3. the actual AMFI raw files preserved on disk;
4. FundLens's audited `RESULTS.md` counts, treated as prior documented evidence, not as a fresh query.

A fresh read-only query is **not** an M0/M1 requirement and is **not** claimed to have been executed. The raw-file fallback is the authoritative extraction path for this project.

---

## 2. Verified FundLens objects

The following definitions were read from:

- `fundlens/sql/migrations/001_raw_layer.sql`
- `fundlens/sql/migrations/002_staging_layer.sql`
- `fundlens/sql/migrations/003_core_layer.sql`
- `fundlens/src/fundlens/ingestion/parser.py`
- `fundlens/src/fundlens/ingestion/loader.py`
- `fundlens/config/scope.toml`
- `fundlens/docs/DATA_CARD.md`
- `fundlens/docs/DECISIONS.md`
- `fundlens/RESULTS.md`

### 2.1 Scheme identity

```sql
CREATE TABLE core.dim_scheme (
    scheme_id        BIGSERIAL PRIMARY KEY,
    amfi_code        TEXT NOT NULL UNIQUE,
    scheme_name      TEXT NOT NULL,
    amc_name         TEXT,
    category         TEXT NOT NULL,
    category_raw     TEXT NOT NULL,
    plan_type        TEXT NOT NULL CHECK (plan_type IN ('DIRECT', 'REGULAR', 'UNKNOWN')),
    option_type      TEXT NOT NULL CHECK (option_type IN ('GROWTH', 'IDCW', 'UNKNOWN')),
    isin             TEXT,
    first_nav_date   DATE,
    last_nav_date    DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Verified identity rule:** the AMFI scheme code (`amfi_code`) identifies one share class (plan + option) and is stable across names. Name similarity is never used to merge schemes.

### 2.2 Renames and mappings

```sql
CREATE TABLE core.scheme_name_history (
    scheme_id    BIGINT NOT NULL REFERENCES core.dim_scheme (scheme_id),
    scheme_name  TEXT NOT NULL,
    first_seen   DATE NOT NULL,
    last_seen    DATE NOT NULL,
    PRIMARY KEY (scheme_id, scheme_name)
);

CREATE TABLE core.scheme_mapping (
    mapping_id       BIGSERIAL PRIMARY KEY,
    from_scheme_id   BIGINT NOT NULL REFERENCES core.dim_scheme (scheme_id),
    to_scheme_id     BIGINT NOT NULL REFERENCES core.dim_scheme (scheme_id),
    relation_type    TEXT NOT NULL CHECK (relation_type IN ('RENAME', 'MERGE', 'SPLIT', 'REPLACED_BY')),
    effective_date   DATE,
    evidence         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'CANDIDATE'
                     CHECK (status IN ('CANDIDATE', 'CONFIRMED', 'REJECTED')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_scheme_id <> to_scheme_id),
    UNIQUE (from_scheme_id, to_scheme_id, relation_type)
);
```

**Verified mapping rule:** every observed name is preserved; explicit relationships require evidence and are never auto-confirmed. This project consumes the resulting stable scheme code and records a mapping-version hash.

### 2.3 NAV observation

```sql
CREATE TABLE core.fact_nav (
    scheme_id   BIGINT NOT NULL REFERENCES core.dim_scheme (scheme_id),
    nav_date    DATE NOT NULL REFERENCES core.dim_date (cal_date),
    nav         NUMERIC(20, 6) NOT NULL,
    file_id     BIGINT NOT NULL REFERENCES raw.source_file (file_id),
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scheme_id, nav_date)
);
```

**Verified value/date rule:** NAV is `NUMERIC(20,6)`; date is `DATE`; one observation per scheme and date. A later conflicting observation is recorded in `core.nav_revision_conflict`, not silently applied.

### 2.4 Source provenance

```sql
CREATE TABLE raw.source_file (
    file_id             BIGSERIAL PRIMARY KEY,
    run_id              BIGINT REFERENCES raw.ingestion_run (run_id),
    source_name         TEXT NOT NULL DEFAULT 'AMFI',
    source_url          TEXT NOT NULL,
    retrieved_at        TIMESTAMPTZ NOT NULL,
    from_date           DATE NOT NULL,
    to_date             DATE NOT NULL,
    http_status         INTEGER NOT NULL,
    file_path           TEXT NOT NULL,
    sha256              CHAR(64) NOT NULL,
    byte_size           BIGINT NOT NULL,
    lines_total         BIGINT NOT NULL,
    data_lines_total    BIGINT NOT NULL,
    lines_in_scope      BIGINT NOT NULL,
    lines_out_of_scope  BIGINT NOT NULL,
    lines_malformed     BIGINT NOT NULL,
    scope_config_hash   CHAR(64) NOT NULL,
    CONSTRAINT uq_source_file_sha UNIQUE (sha256),
    CHECK (from_date <= to_date)
);
```

**Verified provenance rule:** every NAV row is traceable to a source file through `file_id`; the source file records URL, retrieval time, range, HTTP status, path, SHA-256, byte size, line counts and the scope-config hash.

### 2.5 Scope

From `config/scope.toml`:

- Plans: `DIRECT`, `REGULAR`. This project consumes **DIRECT** only for its primary synthetic accounts; `REGULAR` may be used only as an explicitly labelled sensitivity input if approved.
- Options: `GROWTH` only.
- Categories: Large Cap, Large & Mid Cap, Mid Cap, Small Cap, Multi Cap, Flexi Cap, Focused, Value, Contra, Dividend Yield, ELSS.
- AMFI source endpoint: `https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx`, queried with `frmdt` / `todt` in `%d-%b-%Y` format.
- History start: 2006-04-01; earlier requests return an HTML page.

---

## 3. Source-file verification performed

The raw AMFI files under `fundlens/data/raw/amfi/` were read directly with gzip, without importing or executing FundLens.

### 3.1 File integrity

- **86 gzip files** were present on disk.
- They cover **85 distinct date ranges**. The range `2006-06-30 .. 2006-09-27` appears twice with different content hashes:
  - `amfi_nav_20060630_20060927_7101b03da5bb.txt.gz`
  - `amfi_nav_20060630_20060927_f09f872ef68e.txt.gz`
- Every filename's 12-hex SHA-256 prefix matched the SHA-256 of its **uncompressed** content. The verification scanned all 86 files.

Example full checksums:

| File | Compressed bytes | SHA-256 of uncompressed content |
|---|---:|---|
| `amfi_nav_20260913_20261107_6456380a3bb5.txt.gz` | 2,333,893 | `6456380a3bb559c8f27164f420c0dddd95ec4a2b8f640e2a135437b631fcaea8` |
| `amfi_nav_20060630_20060927_7101b03da5bb.txt.gz` | 748,448 | `7101b03da5bbe63df416a6dc6fbf2ba18f8bcb0bf6bda87f171af968174475aa` |
| `amfi_nav_20060630_20060927_f09f872ef68e.txt.gz` | 748,454 | `f09f872ef68e92c69d0a3bc8d7eafab8ae7158483ced0ea7768b81087a7ce15c` |

### 3.2 Duplicate-range difference

The two 2006 files have the same total line count (124,427) and the same 8-field data line count (123,328). They differ on only three NAV values, all for the **out-of-scope IDCW** scheme `100793` (Sundaram Banking and PSU Debt Fund Regular Plan - IDCW) on 26-Jul-2006, 18-Aug-2006 and 29-Aug-2006. No Growth-plan row differs. The full row-level comparison is in `docs/FUNDLENS_FILE_RECONCILIATION.md`.

This is a genuine AMFI restatement/conflict example. It does not affect this project's Growth-only input, but it confirms why the adapter must record conflicts rather than overwrite.

### 3.3 Observed coverage

A read-only scan of all 86 files produced:

| Metric | Observed value |
|---|---:|
| Data lines parsed (8-field semicolon rows) | 38,321,040 |
| In-scope rows in the 11 categories (all plans/options, per file) | 3,916,242 |
| Unique in-scope `(scheme_code, nav_date)` observations | 3,833,130 |
| Direct-Growth rows in those categories (per file) | 798,178 |
| Unique Direct-Growth `(scheme_code, nav_date)` observations | 781,277 |
| First Direct-Growth observation in sampled long-history schemes | 2013-01-02 |
| Last observation in the latest file | 2026-11-06 |

These are the reconciliation-scan figures from `docs/FUNDLENS_FILE_RECONCILIATION.md`. An earlier draft's Direct-Growth figure of 435,745 is withdrawn; it was not reproduced.

FundLens's audited `RESULTS.md` reports a different snapshot basis:

- 85 registered source files;
- 1,811,703 `core.fact_nav` rows;
- 779 schemes (375 Direct, 404 Regular);
- NAV date range 2006-04-02 to 2026-11-06.

The difference between “86 files on disk” and “85 registered” is consistent with the duplicate 2006 range: one of the two files need not have been registered. Vicky requires this to be reconciled with filenames, checksums, date ranges and row-level differences before M0 closes, and recorded in the pipeline provenance. It is not a reason to trust one count over the other; both are reported. Do not silently omit or alter either source record.

### 3.4 Representative long-history schemes

The following Direct-Growth schemes were verified to have continuous observations from 2013 to 2026 in the raw files. They are suitable candidates for synthetic accounts and sensitivity paths, subject to the final eligibility rule in `config/sensitivity.yaml`.

| Category | AMFI code | Name as received | Observed n | First | Last |
|---|---|---|---:|---|---|
| Large Cap | 119528 | Aditya Birla Sun Life Large Cap Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| Large Cap | 119250 | DSP Large Cap Fund - Direct Plan - Growth | 3,411 | 2013-01-02 | 2026-11-06 |
| Large & Mid Cap | 119436 | Aditya Birla Sun Life Large & Mid Cap Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| Large & Mid Cap | 118419 | Bandhan Large & Mid Cap Fund - Direct Plan - Growth | 3,419 | 2013-01-02 | 2026-11-06 |
| Mid Cap | 119620 | Aditya Birla Sun Life Midcap Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| Mid Cap | 119071 | DSP Midcap Fund - Direct Plan - Growth | 3,411 | 2013-01-02 | 2026-11-06 |
| Small Cap | 119556 | Aditya Birla Sun Life Small Cap Fund - Growth - Direct Plan | 3,406 | 2013-01-07 | 2026-11-06 |
| Small Cap | 119212 | DSP Small Cap Fund - Direct Plan - Growth | 3,411 | 2013-01-02 | 2026-11-06 |
| Flexi Cap | 120564 | Aditya Birla Sun Life Flexi Cap Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| Flexi Cap | 118424 | BANDHAN Flexi Cap Fund-Direct Plan-Growth | 3,419 | 2013-01-02 | 2026-11-06 |
| Focused | 119564 | Aditya Birla Sun Life Focused Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| Focused | 119096 | DSP Focused Fund - Direct Plan - Growth | 3,411 | 2013-01-02 | 2026-11-06 |
| Value | 118481 | Bandhan Value Fund - Direct Plan - Growth | 3,419 | 2013-01-02 | 2026-11-06 |
| Value | 120323 | ICICI Prudential Value Fund (erstwhile Value Discovery Fund) - Direct Plan - Growth | 3,409 | 2013-01-02 | 2026-11-06 |
| Contra | 119769 | Kotak Contra Fund - Direct Plan - Growth | 3,409 | 2013-01-02 | 2026-11-06 |
| Contra | 119835 | SBI CONTRA FUND - DIRECT PLAN - GROWTH | 3,419 | 2013-01-02 | 2026-11-05 |
| Dividend Yield | 119507 | Aditya Birla Sun Life Dividend Yield Fund - Growth - Direct Plan | 3,408 | 2013-01-02 | 2026-11-05 |
| Dividend Yield | 118527 | Franklin India Dividend Yield Fund - Direct - Growth | 3,408 | 2013-01-01 | 2026-11-05 |
| ELSS | 119544 | Aditya Birla Sun Life ELSS Tax Saver Fund - Growth - Direct Plan | 3,409 | 2013-01-02 | 2026-11-06 |
| ELSS | 119242 | DSP ELSS Tax Saver Fund - Direct Plan - Growth | 3,411 | 2013-01-02 | 2026-11-06 |
| Multi Cap | 148921 | Aditya Birla Sun Life Multi-Cap Fund-Direct Growth | 1,357 | 2021-05-10 | 2026-11-06 |
| Multi Cap | 152310 | DSP Multi Cap Fund - Direct - Growth | 684 | 2024-01-31 | 2026-11-06 |

The Multi Cap category was redefined by SEBI in 2017; older “multi cap” schemes may sit under other categories. The eligibility rule must therefore be applied from the data, not from assumptions.

---

## 4. Canonical NAV export contract

### 4.1 Database extraction query (documented, not used under Option A)

> **Option A decision:** this query is not executed for this project. It is retained as documentation of the FundLens schema and as a future comparison artefact only. Do not run it against FundLens or its volumes. The primary extraction is the raw-file fallback in section 4.3.

The following query would produce the canonical CSV from FundLens if database access were ever explicitly authorised. It would require a read-only transaction and must not write to FundLens.

```sql
SELECT
    s.amfi_code                         AS scheme_code,
    s.scheme_name                       AS scheme_name,
    s.amc_name                          AS amc_name,
    s.category                          AS category,
    s.plan_type                         AS plan_type,
    s.option_type                       AS option_type,
    s.isin                              AS isin,
    f.nav_date                          AS nav_date,
    f.nav::text                         AS nav,
    f.file_id                           AS source_file_id,
    sf.sha256                           AS source_sha256,
    sf.source_url                       AS source_url,
    sf.retrieved_at                     AS retrieved_at,
    f.loaded_at                         AS loaded_at,
    sf.scope_config_hash                AS scope_config_hash
FROM core.fact_nav f
JOIN core.dim_scheme s
  ON s.scheme_id = f.scheme_id
JOIN raw.source_file sf
  ON sf.file_id = f.file_id
WHERE s.option_type = 'GROWTH'
  AND s.plan_type IN ('DIRECT')          -- add 'REGULAR' only for a labelled sensitivity export
  AND s.category IN (
      'Large Cap', 'Large & Mid Cap', 'Mid Cap', 'Small Cap', 'Multi Cap',
      'Flexi Cap', 'Focused', 'Value', 'Contra', 'Dividend Yield', 'ELSS'
  )
ORDER BY s.amfi_code, f.nav_date;
```

The consumer must open the connection with `SET TRANSACTION READ ONLY` and must not call any FundLens migration, ingestion or write path.

### 4.2 CSV schema

| Column | Type | Required | Semantics |
|---|---|---|---|
| `scheme_code` | text | yes | Stable AMFI scheme code; primary identity. |
| `scheme_name` | text | yes | Name as received at the observation/latest observation; may change over time. |
| `amc_name` | text | no | Asset management company name. |
| `category` | text | yes | FundLens-normalised category. |
| `plan_type` | text | yes | `DIRECT` or `REGULAR`. |
| `option_type` | text | yes | `GROWTH` for this project. |
| `isin` | text | no | ISIN as published, if present. |
| `nav_date` | ISO date | yes | `YYYY-MM-DD`. |
| `nav` | decimal string | yes | As published, stored as `NUMERIC(20,6)`; no binary float. |
| `source_file_id` | integer | yes | FundLens `raw.source_file.file_id`. |
| `source_sha256` | 64-hex text | yes | SHA-256 of the uncompressed source file. |
| `source_url` | text | yes | AMFI request URL. |
| `retrieved_at` | ISO timestamp | yes | FundLens retrieval time (UTC). |
| `loaded_at` | ISO timestamp | yes | FundLens import time (UTC). |
| `scope_config_hash` | 64-hex text | yes | Hash of the FundLens scope config used for the file. |

The CSV file itself is accompanied by a manifest:

```json
{
  "contract_version": "1.0",
  "extraction": "raw_file_fallback",
  "generated_at": "2026-11-09T00:00:00Z",
  "parser_sha256": "<sha256 of the FundLens parser file used>",
  "scope_config_sha256": "<sha256 of the FundLens scope config>",
  "fundlens_git_commit": "<commit or null if unavailable>",
  "source_file_count": 86,
  "source_files": [
    {
      "filename": "amfi_nav_YYYYMMDD_YYYYMMDD_<hashprefix>.txt.gz",
      "uncompressed_sha256": "<64-hex>",
      "from_date": "YYYY-MM-DD",
      "to_date": "YYYY-MM-DD",
      "data_lines_total": 0
    }
  ],
  "row_count": 435745,
  "distinct_schemes": 200,
  "min_nav_date": "2013-01-01",
  "max_nav_date": "2026-11-06",
  "file_sha256": "<sha256 of the CSV bytes>",
  "fundlens_schema_migrations": ["001_raw_layer.sql", "002_staging_layer.sql", "003_core_layer.sql"],
  "notes": "Raw-file fallback; no FundLens database or volume access; no FundLens modification."
}
```

### 4.3 Primary extraction: preserved raw files (Option A)

The consumer builds the canonical CSV from the preserved raw AMFI files by using FundLens's **verified parser and scope config as a read-only reference**. This is the primary extraction path, not a second mapping implementation:

- use `fundlens.ingestion.parser.parse_lines` and `fundlens.config.load_scope` with `PYTHONDONTWRITEBYTECODE=1`;
- never write inside the FundLens directory;
- record the FundLens git commit and the parser/scope file hashes in the manifest;
- record every source file's uncompressed SHA-256, filename, date range and row counts;
- produce the identical CSV schema;
- label the manifest `"extraction": "raw_file_fallback"`.

The fallback must be reconciled against FundLens's audited `RESULTS.md` counts and tested against the fixture appendix. It must not silently diverge, omit a source record or alter a NAV value.

### 4.4 Import validation

The consumer adapter must:

1. verify the manifest and CSV SHA-256;
2. parse all decimals as `Decimal`, never `float`;
3. reject non-positive, non-finite or malformed NAVs;
4. reject rows outside the configured plan/option/category scope;
5. reject duplicate `(scheme_code, nav_date)` rows with different NAV values;
6. detect a conflicting NAV for an already-imported `(scheme_code, nav_date)` and record it in `nav_revision_conflict`, keeping the original value;
7. record source file, retrieval time, import time, scope hash and validation outcome per row or per batch;
8. create an immutable `nav_snapshot` with row count, min/max date, content hash and manifest hash;
9. be idempotent: re-importing an identical manifest/CSV is a no-op;
10. fail non-zero on invalid data, not silently skip it.

---

## 5. Scheme mapping and rename behaviour

- The project keys schemes by `scheme_code` (AMFI code). It never merges schemes by name.
- `scheme_name` is display data; a name change is not an identity change.
- A scheme mapping/rename event is represented by the FundLens mapping version and, if needed, a local `scheme_mapping_version` string in report snapshots.
- The project must not independently infer a rename from name similarity.
- If a scheme is merged or replaced, the mapping must be explicit and evidence-backed. Until approved, the project uses the original scheme code and reports the limitation.
- The report snapshot stores the mapping-version hash so a later mapping change cannot silently alter a historical report.

---

## 6. What is verified, and what is not

### Verified

- Table and column names and types via FundLens migration DDL.
- Scheme identity and rename handling via DDL and loader logic.
- AMFI file format and parser behaviour via `parser.py`.
- Source provenance fields via `raw.source_file` DDL.
- Actual raw-file presence, gzip integrity, filename SHA-256 prefixes, duplicate range and coverage.
- Representative Direct-Growth schemes and their date coverage.

### Not yet verified

- Row counts from a live `core.fact_nav` query. This is intentionally out of scope under Option A and is not a gate item.
- The exact FundLens database snapshot used by the audited `RESULTS.md`.
- The reconciliation of 86 files on disk vs 85 registered files, with filenames, checksums, date ranges and row-level differences.
- A live `nav_snapshot` content hash produced by the consumer.

The raw-file fallback is accepted by Vicky as the authoritative M0 extraction basis. The M0 gate still requires the 86-vs-85 reconciliation and Vicky's review of this contract. The contract is usable for design; it must not be described as a live-database verification.

---

## 7. Non-negotiable rules

1. Do not modify FundLens.
2. Do not copy FundLens secrets or `.env` contents.
3. Do not redistribute AMFI data; keep raw and exported files local and git-ignored.
4. Do not fabricate NAV observations or describe synthetic values as real.
5. Do not silently forward-fill NAVs beyond the documented limit.
6. Do not overwrite a conflicting NAV; record it.
7. Do not use name similarity to merge schemes.
8. Do not claim the contract was verified more strongly than the evidence above.
