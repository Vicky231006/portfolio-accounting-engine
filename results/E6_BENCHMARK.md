# E6 — As-of Query Benchmark

| Field | Value |
|---|---|
| Measured at (UTC) | 2026-11-11T06:58:05+00:00 |
| PostgreSQL | PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu |
| Python | 3.12.16 |
| Platform | Windows-11-10.0.26300-SP0 |
| CPU | Intel64 Family 6 Model 183 Stepping 1, GenuineIntel (16 logical cores) |
| Memory | 15.7 GB |
| Database | unknown; image `postgres:16` |
| Rows | accounts 1,000; transactions 209,937; revisions 209,938; NAV observations 1,811,703 |
| Runs | 30 measured + 3 warm-up per point |

The measured statement is the exact as-of SQL used by `LedgerService.get_as_of` (visible revisions at knowledge time `K`).

## Latency (milliseconds)

| Knowledge point | Visible revisions | Without index p50 | Without index p95 | With index p50 | With index p95 | Speed-up p50 |
|---|---:|---:|---:|---:|---:|---:|
| p25 (2019-07-29) | 52,486 | 268.48 | 281.83 | 262.31 | 278.55 | 1.02x |
| p50 (2022-05-05) | 104,970 | 539.27 | 561.32 | 527.07 | 547.99 | 1.02x |
| p75 (2024-06-24) | 157,453 | 795.20 | 822.14 | 792.76 | 873.00 | 1.00x |
| max (2026-10-31) | 209,938 | 1315.60 | 1368.38 | 1299.42 | 1372.61 | 1.01x |

## Query plans

| Knowledge point | Phase | Indexes used | Execution ms |
|---|---|---|---:|
| p25 | without index | (seq scan only) | 97.66 |
| p25 | with index | (seq scan only) | 95.94 |
| p50 | without index | (seq scan only) | 246.87 |
| p50 | with index | (seq scan only) | 177.03 |
| p75 | without index | uq_txn_revision_group_no, txn_business_pkey | 305.51 |
| p75 | with index | uq_txn_revision_group_no, txn_business_pkey | 310.86 |
| max | without index | uq_txn_revision_group_no, txn_business_pkey | 404.64 |
| max | with index | uq_txn_revision_group_no, txn_business_pkey | 375.86 |

Result digests identical with and without the index: **True**.

## Interpretation limits

- Latency is hardware-, cache- and PostgreSQL-configuration-specific. These numbers describe the environment above and are not a portable performance guarantee.
- The benchmark runs the query directly against PostgreSQL; it does not include Python object construction for every column of `get_as_of`.
- The database was local (containerised PostgreSQL 16); network latency is loopback.

## Reproduce

```
python scripts/benchmark_e6.py --allow-index-ddl --runs 30
```
