# Archived E9 evidence — original frozen run (superseded)

These files are the **original** M8/E9 outputs produced on 2026-11-09 with the
frozen configuration `config/sensitivity.yaml` (SHA-256
`93fb380b293e22346df01cbf728a73a957cce8c4798103ffd8c789082ab8ab01`).

They are preserved unchanged for auditability. Do **not** overwrite them.

## Why they were superseded

The 2026-11-11 E9 exclusion investigation found an implementation defect in the
sensitivity helper `returns_for_installments`:

- terminal valuation used the **last NAV date in the whole dataset** rather than
  the last NAV on or before the 12-month window end;
- backdated instalments were shifted by calendar days and silently dropped when
  the shifted date had no NAV;
- the sensitivity-only XIRR solver used a narrower domain (`r ∈ [-0.5, 5]`)
  than the documented production domain (`r ∈ (-0.999999, 1000)`);
- the SIP TWR helper did not chain-link subperiod returns correctly.

The defect made older windows (2016–2019) produce terminal values from 2026
NAVs over a one-day XIRR holding period, which explains the concentration of
386 exclusions in those years.

## Current evidence

The corrected, reproducible outputs live in:

- `results/sensitivity_detail.csv`
- `results/sensitivity_summary.json`
- `results/E9_COVERAGE.md`
- `results/E9_EXCLUSION_ANALYSIS.md`
- `results/E9_EXCLUSION_ANALYSIS.json`

The corrected run uses the same frozen study configuration, same eligible
schemes and same quarterly window grid. Only the documented implementation
defects above were fixed; the metric definition (annualised XIRR minus period
TWR over the same 12-month SIP window) is unchanged.

See `docs/E9_EXCLUSION_INVESTIGATION.md` for the full investigation.
