# Earliest Imported NAV (2006-04-02) — Raw-File Evidence

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Question | Is the earliest imported NAV date `2006-04-02` valid, or is it a parse error for assuming it must be a business day? |
| Conclusion | **Verified valid.** Every source row was found verbatim in the original raw file. The date was not assumed invalid from its weekday. |
| Verified during | M2 (pre-M2 acceptance evidence) |
| Date | 2026-11-09 |

---

## 1. What was imported

The M1 import (snapshot `amfi_nav_m1`) has minimum `nav_date = 2006-04-02`. The weekday of 2006-04-02 is Sunday. AMFI NAV history reports the NAV as published for that date; absence of a business-day rule means a Sunday date alone is not evidence of invalidity.

The raw file for the imported window is:

- `data/raw/amfi/2006/amfi_nav_20060401_20060629_c6beb9fb99bb.txt.gz`
- Uncompressed SHA-256 (per M0 verification and the M1 import manifest): `c6beb9fb99bbea6bafb41096498a65f3b01584af277a048e02b99430218173e6`
- Relevant full checksum (M1 import): `c6beb9fb99bbea6bafb41096498a65f3b01584af277a048e02b99430218173e6` (prefix `c6beb9fb99bb` matches the filename).
- CSV line counts (M0): 124,427 lines total; 123,328 8-field data lines.

All 7 in-scope observations with `nav_date = 2006-04-02` were verified:

| Scheme code | Imported NAV (`core.nav_observation.nav`) | Verbatim raw-file line (8-field, `DD-Mon-YYYY`) |
|---|---|---|
| 100349 | 82.66 | `100349;ICICI Prudential Large & Mid Cap Fund - Growth;Regular Plan;Growth;INF109K01431;;82.66;02-Apr-2006` |
| 100350 | 10.85 | `100350;ICICI Prudential Large & Mid Cap Fund - Institutional Option - I - Growth;;;INF109K01456;;10.85;02-Apr-2006` |
| 100354 | 90.70 | `100354;ICICI Prudential ELSS - Tax Saver Fund - Growth;Regular Plan;Growth;INF109K01464;;90.70;02-Apr-2006` |
| 101228 | 70.34 | `101228;ICICI Prudential Multi Cap Fund - Growth;Regular Plan;Growth;INF109K01613;;70.34;02-Apr-2006` |
| 102528 | 25.36 | `102528;ICICI Prudential Mid Cap Fund - Growth;Regular Plan;Growth;INF109K01AN2;;25.36;02-Apr-2006` |
| 102594 | 25.84 | `102594;ICICI Prudential Value Fund (erstwhile Value Discovery Fund) - Growth;Regular Plan;Growth;INF109K01AF8;;25.84;02-Apr-2006` |
| 102596 | 10.87 | `102596;ICICI Prudential Value Discovery Fund - Institutional Option - I - Growth;;;INF109K01AE1;;10.87;02-Apr-2006` |

Raw file line numbers (gz decompressed, 1-indexed):

| Scheme code | Raw line number |
|---|---|
| 100349 | 42720 |
| 100350 | 42842 |
| 100354 | 100727 |
| 101228 | 97606 |
| 102528 | 98530 |
| 102594 | 45840 |
| 102596 | 45779 |

All values match the imported `core.nav_observation` rows exactly (amounts as published, stored `NUMERIC(20,6)`). The last field `02-Apr-2006` is the AMFI-published date for every row.

## 2. Why the earliest date is 2006-04-02, not 2006-04-01

The file's nominal range starts `2006-04-01`, and FundLens's history start is `2006-04-01` (see `docs/DATA_CARD.md`). The earliest **data** row for a scheme in the 11-category scope is `2006-04-02`. Rows dated `01-Apr-2006` exist in the raw file, but belong to schemes outside the 11-category Directed-Growth scope or are otherwise excluded by scope/duplicate rules in the M1 import. The imported minimum is therefore `2006-04-02`, and it is verified against the raw source.

No synthetic, adjusted or forward-filled date was created. The consumer did not treat the Sunday date as an error.

## 3. Reproduction

The check was performed by:

1. Querying `core.nav_observation` for `snapshot_id = 3` and `nav_date = '2006-04-02'` (7 rows, all `option_type = 'GROWTH'`).
2. Decompressing the raw file read-only and searching for the 8-field lines whose date field equals `02-Apr-2006` and whose scheme codes are among the 7 imported codes.
3. Confirming each NAV value matches verbatim.

The FundLens source was opened read-only (mounted `ro`); no FundLens file, database, volume or secret was modified.

## 4. Limits

- This verifies the 7 in-scope observations dated 2006-04-02 only. It does not claim anything about non-scope rows dated 2006-04-01 or about scheme categories outside the 11-category scope.
- It does not change the M1 import counts (1,811,703 rows). The earliest date remains 2006-04-02.
