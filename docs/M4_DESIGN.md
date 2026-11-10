# M4 Design Review — Positions and Valuation

| Field | Value |
|---|---|
| Milestone | M4 — Positions and Valuation (PRD §5.3, §8; FR-B5, FR-B6) |
| Status | Design for implementation (authorised by Vicky 2026-11-09) |
| Date | 2026-11-09 |

---

## Purpose

M4 answers two questions for any `(account_id, valid_date, known_as_of)` triple: **what cash and units does the account hold as of that date, given only what was known then**, and **what is that portfolio worth using the M1 NAV snapshot**? It does not compute returns (M5) and does not persist holdings.

It consumes the frozen M1–M3 contracts: M2's generator output (instructions only), M3's revision ledger (`get_as_of`), and the M1 NAV snapshot (immutable). The M2 generator never wrote derived facts; the M3 correction engine never valued a position — this milestone is the first that does.

## 1. Position derivation

`ValuationService.positions(account_id, valid_date, known_as_of)`:

1. `LedgerService.get_as_of(known_as_of)` → the **visible revisions** at knowledge time K (`VOIDED` excluded). The current projection `txn_version_current` is never read — otherwise K1/K2 collapse.
2. Filter to the account. Expand each visible revision into posting legs using the same rule set as M3's validity replay (D-049), on the assumption that corrections were already validated by M3 — but re-check intermediates anyway (see §5).
3. Sort legs by **`(posting_date, posting_sequence, txn_group_id)`** — the M3 replay key (D-027, verification supplement D). `recorded_at` never orders legs.
4. Include only legs with `posting_date <= valid_date`. Apply them to `cash: Decimal = 0`, `units: dict[scheme, Decimal] = {}`.

| Type | Legs (posting date = leg's own NAV date) |
|---|---|
| CONTRIBUTION | `cash += amount` on `effective_date` |
| WITHDRAWAL | `cash -= amount` on `effective_date` |
| PURCHASE | `cash -= actual_cash; units[scheme] += units` on `allotment_date` |
| REDEMPTION | `cash += proceeds; units[scheme] -= units` on `allotment_date` |
| SIP_INSTALMENT | `cash += amount` on `effective_date`; purchase legs on `allotment_date` |
| SWITCH | source redemption on `source_nav_date`; target purchase + `residual` cash on `target_allotment_date` |

Units/proceeds are the M3/METHODOLOGY §3 derivations (`ROUND_DOWN` purchase units, `ROUND_HALF_UP` cash, switch residual ≥ 0 — D-026). Positions are **returned** as immutable dataclasses (`PositionsResult`), never written to a table.

## 2. Cash treatment

Cash is a first-class balance, not a plug. It starts at zero (D-027: opening funding is an explicit `CONTRIBUTION`). There is no overdraft. Every cash delta above is the exact Decimal that the corresponding leg moves. The valuation returns `cash` separately from holding values so a reviewer can always see the split.

## 3. NAV selection (D-050)

`ValuationService.value(account_id, valid_date, known_as_of, stale_limit_days=5)` calls `positions(...)` first, then prices each holding from `core.nav_observation` for the service's `nav_snapshot_id`:

```sql
SELECT nav, nav_date FROM core.nav_observation
WHERE nav_snapshot_id = %s AND amfi_scheme_code = %s AND nav_date <= %s
ORDER BY nav_date DESC LIMIT 1
```

- `price_date == valid_date` → fresh (`is_stale = False`).
- `1 <= (valuation_date − price_date).days <= stale_limit` → **stale-carried**, flagged per holding, counted in `stale_value`.
- Latest NAV **6+ days old**, or no NAV at/before the date → the whole valuation raises `ValuationError(STALE_BEYOND_LIMIT | MISSING_NAV)` — **no partial value, no silent fill**.

Every valued holding becomes a `ValuedHolding(scheme_code, units, price, price_date, is_stale, stale_days, value)`. Scheme identity is the AMFI code only; FundLens mapping is never re-interpreted and names are never merged.

## 4. Reconciliation approach (D-051)

`portfolio_value = cash + Σ(holding.value)` where each `holding.value = (units × price).quantize(0.01, ROUND_HALF_UP)` and the result also reports `fresh_value` / `stale_value` with the assertion `fresh_value + stale_value == holdings_value` in `Decimal` arithmetic — any mismatch raises `RECONCILIATION_FAILED`. The same replay that produces positions also validates intermediates: a negative cash or units figure at any leg raises `INVARIANT_FAILED`, so the reconciliation covers the *path*, not just the endpoint. All arithmetic is `Decimal`; PostgreSQL supplies `NUMERIC`. No `float` appears anywhere (and the test suite greps for it).

## 5. Historical reconstruction (K1/K2)

Because positions derive from `get_as_of(K)`, a correction recorded after K1 changes the K2 holdings at the same `valid_date` while leaving K1 untouched — the exact PRD §2.2 property. Scheme changes via `REVERSE_AND_REPLACE` therefore move the K2 units from the old scheme code to the new one; K1 still reports the old holding.

## 6. API surface

```
positions(account_id, valid_date, known_as_of) -> PositionsResult
    cash: Decimal, holdings: tuple[Holding], as_of_revision_count: int
value(account_id, valid_date, known_as_of, stale_limit_days=5) -> ValuationResult
    positions + holdings: tuple[ValuedHolding], fresh_value, stale_value,
    portfolio_value, stale_holdings (subset)
```

Both are deterministic: same arguments → same `Decimal`s, same order (holdings sorted by `scheme_code`). Repeated queries are byte-identical by construction (no wall-clock, no iteration-order dependence).

## 7. Testing plan (FR-B5/B6 acceptance)

| Requirement | Test |
|---|---|
| Contributions & withdrawals | cash trajectory exact |
| Purchases & redemptions | derived units / proceeds match METHODOLOGY hand calculations |
| SIP linked legs | contribution date ≠ purchase date: interim cash visible, single external funding |
| Switch with split NAV dates | interim source cash; target priced on its own date; residual once |
| Multiple schemes / accounts | independent per-account dicts; same scheme, two accounts, separate balances |
| K1/K2 reconstruction | correction changes K2 positions/valuation, K1 unchanged |
| Missing / stale NAV | stale ≤5d succeeds flagged; 6d and none-at-all raise distinct errors |
| Negative / invalid cash | helper-injected negative history raises invariant error |
| Position↔valuation reconciliation | sum assertion + independent hand total |
| Determinism | same query twice → equal results |

## 8. Non-goals (explicit)

No TWR, no Modified Dietz, no XIRR, no sensitivity, no snapshots, no dashboard. The stale policy constant (5 days) is a parameter with the approved default; different limits can be passed per call but the default is what is tested.
