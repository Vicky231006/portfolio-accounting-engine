# Methodology and Hand-Computed Fixtures

| Field | Value |
|---|---|
| Project | `bitemporal-ledger` — Portfolio Accounting & Performance Engine |
| Status | Approved by Vicky 2026-11-09, after the four final documentation amendments were completed; M0 exit gate met and formally recorded as approved. No production financial formula may be implemented until the M1 foundations gate passes. |
| Date | 2026-11-09 |
| Source | PRD v2.0 sections 5–8, 10, 12; `docs/M0_DESIGN_REVIEW.md` |
| Arithmetic | Python `Decimal`, PostgreSQL `NUMERIC`; no binary floating point in financial paths |

This document defines the accounting, valuation, performance, rounding, temporal and replay conventions. Every production formula must be implemented only after a fixture here has been computed independently.

---

## 1. Notation and sign conventions

| Symbol | Meaning |
|---|---|
| `S` | Period start: `start_date 00:00:00` (midnight at the start of the first calendar day in the period). |
| `E` | Period end: `(end_date + 1 day) 00:00:00` (midnight immediately after the last calendar day in the period). |
| `V_t` | End-of-day portfolio value on date `t`: cash + sum of position values. |
| `V_S` | Portfolio value at the start of `S`, before any flow on `S`. |
| `V_E` | Portfolio value at the end of `E`, after all flows and market movement through `end_date`. |
| `CF_t` | Net external flow on date `t`, signed from the **portfolio** perspective: contribution positive, withdrawal negative. |
| `CF_i` | The `i`-th external flow in a period. |
| `T` | Number of calendar days in the period, inclusive: `(E - S).days`. |
| `t_i` | Calendar days from `S` to the date of `CF_i`: `(d_i - S).days`. |
| `w_i` | Modified Dietz weight: `(T - t_i) / T`. |
| `r_t` | Subperiod return. |
| `NAV` | Published net asset value per unit, as a decimal. |
| `bp` | Basis point: `0.0001` as a decimal fraction, or `0.01` percentage point. |

**External flows** are contributions and withdrawals between the investor and the portfolio. Contributions are positive; withdrawals are negative.

**Internal movements** are purchases, redemptions and switches between cash and fund units. They are never external flows.

A `SIP_INSTALMENT` has a contribution leg (external, counted once) and a purchase leg (internal). A `SWITCH` is a linked redemption and purchase, entirely internal.

---

## 2. Date semantics

Three dates must never be conflated:

| Date | Meaning | Accounting effect |
|---|---|---|
| `instruction_date` | When the order was initiated. | Audit only; no posting. |
| `effective_date` | The business date on which the transaction group's accounting effect is posted. | Cash and/or unit legs post. |
| `allotment_date` | The NAV date used to derive units or proceeds. | Determines the price. |

### 2.1 Simple purchase and redemption

Recommended v1 rule:

- `allotment_date` is the first date on or after the instructed effective date for which the scheme has a NAV, within **5 calendar days**.
- If no NAV exists within the limit, the transaction is not created; a correction that would require one is rejected.
- For a simple purchase or redemption, the **posting date is the allotment date**, so cash and units move together. The original instruction date is retained for audit.
- A purchase with an instructed amount `A` and allotment NAV `P` has `units = round_down(A / P, 3)` and `actual_cash = round_half_up(units × P, 2)`. The residual `A - actual_cash` remains in cash and is recorded.
- A redemption with instructed units `U` and allotment NAV `P` has `proceeds = round_half_up(U × P, 2)`.

### 2.2 SIP instalment

- The contribution leg posts on the **contribution date** (for example, the 5th).
- The linked purchase leg posts on its **allotment date** (the first NAV date on or after the contribution date, within the limit).
- Interim cash is visible and valued between the two dates.
- The external flow is the contribution amount, counted exactly once. The purchase is internal.
- If the purchase cannot be priced within the limit, the whole SIP instalment group is rejected; the contribution is not left dangling.

### 2.3 Switch

A switch is one atomic group:

1. Redeem the instructed source units.
2. Compute source proceeds using the source-scheme NAV.
3. Purchase the target scheme using those proceeds.
4. Compute target units using the target-scheme allotment NAV.
5. Credit any residual cash to the account.

Recommended v1 date rule:

- `switch_date` is the effective date of the instruction.
- `source_nav_date` is the first source-scheme NAV date on or after `switch_date`, within 5 calendar days.
- `target_allotment_date` is the first target-scheme NAV date on or after `source_nav_date`, within 5 calendar days.
- The source redemption posts on `source_nav_date`; the target purchase posts on `target_allotment_date`.
- Interim cash from the source redemption is visible and valued.
- If either leg cannot be priced within the limit, neither posts. The group is atomic in the database transaction.
- The switch is never an external contribution or withdrawal.

### 2.4 Correction

- A correction carries its own `recorded_at` (knowledge time) and may be backdated in effective date.
- It changes only instruction fields: effective date, amount or units, scheme via reverse-and-replace.
- Derived NAV, units, proceeds and cash legs are recomputed atomically for the whole group.
- Units are never edited directly.
- The prior revision remains queryable at earlier knowledge times.
- If the corrected history would create negative units or cash at any later effective date, the entire correction group is rejected and logged.

### 2.5 Same-effective-date posting sequence

Same-effective-date ordering is explicit, not inferred from transaction type:

- Every transaction group has an integer `posting_sequence` for its account and effective date.
- Groups are processed in ascending `posting_sequence`; ties are broken deterministically by immutable group ID.
- There is no universal transaction-type priority. A contribution, withdrawal, purchase or switch can appear at any sequence position.
- Each group is atomic. If it would create negative cash or units, it is rejected with `INSUFFICIENT_CASH` or `INSUFFICIENT_UNITS`, nothing from that group posts, and the rejection is recorded.
- Later groups are evaluated against the actual posted balances, not against a hypothetical end-of-day state.
- A SIP contribution must be sequenced before its linked purchase if the purchase is to use that cash. A switch is one group, not two independently sequenced legs.
- Changing `posting_sequence` is a correction and must preserve the prior revision and knowledge time.

**Why this matters:** a hardcoded contributions-first rule would let a withdrawal succeed that the producer intended to reject, and would then reject a later purchase. That changes the reported holdings even though the end-of-day total cash may look similar. The explicit sequence makes the intended intraday dependency auditable.

### 2.6 Inclusive full-calendar-day period boundaries and flow timestamps

Vicky adopted the inclusive full-calendar-day convention for all period and flow arithmetic:

- Period start `S = start_date 00:00:00` (midnight at the start of the first calendar day in the period).
- Period end `E = (end_date + 1 day) 00:00:00` (midnight immediately after the last calendar day in the period).
- Opening valuation is before events on the start date: at `S`, before any flow on `start_date`.
- Closing valuation includes events through the end date and the market move on `end_date`: at `E`, i.e., after a flow on `end_date` (start of day) and the resulting position value.
- External flows are timestamped at start of day; a flow on `start_date` is at `S`; a flow on `end_date` is at `end_date 00:00`, and the closing valuation is at `E = end_date + 1 day 00:00`.
- `T = (E - S).days` equals the inclusive calendar-day count of the period.
- `t_i = (d_i - S).days` for a flow dated `d_i` at start of day.

The fixtures below use this convention consistently.

---

## 3. Rounding and residual cash

### 3.1 Precision

| Quantity | Precision | Storage | Rounding |
|---|---|---|---|
| NAV | As published | `NUMERIC(20,6)` | None in calculation; preserve source decimal. |
| Units | 3 decimal places | `NUMERIC(20,3)` | `ROUND_DOWN` for amount-instructed purchases; `ROUND_HALF_UP` for other unit calculations. |
| Currency amounts | 2 decimal places | `NUMERIC(20,2)` | `ROUND_HALF_UP`. |
| Returns | 10 decimal places as a decimal fraction | `NUMERIC(18,10)` | Round only for storage/display, never inside a formula. |
| Basis points | Derived for display | — | `return × 10,000`. |

### 3.2 Why amount-instructed purchase units use ROUND_DOWN

If units are rounded up, `units × NAV` can exceed the instructed amount, forcing a debit larger than the investor authorised. If units are rounded down, `actual_cash = round_half_up(units × NAV, 2) <= instructed_amount`, so the purchase is always self-funding. The difference stays in cash and is recorded as a rounding residual.

This is a deliberate exception to the general `ROUND_HALF_UP` mode. The published NAV precision is never changed.

### 3.3 Purchase

```
raw_units       = instructed_amount / allotment_nav
units           = quantize(raw_units, 3, ROUND_DOWN)
actual_cash     = quantize(units × allotment_nav, 2, ROUND_HALF_UP)
rounding_residual = instructed_amount - actual_cash   (>= 0)
cash_after      = cash_before - actual_cash
```

The transaction stores `instructed_amount`, `units`, `allotment_nav`, `actual_cash` and `rounding_residual`.

### 3.4 Redemption

```
proceeds = quantize(instructed_units × allotment_nav, 2, ROUND_HALF_UP)
cash_after = cash_before + proceeds
```

### 3.5 Switch

```
source_proceeds = quantize(source_units × source_nav, 2, ROUND_HALF_UP)
target_units    = quantize(source_proceeds / target_nav, 3, ROUND_DOWN)
target_cost     = quantize(target_units × target_nav, 2, ROUND_HALF_UP)
residual_cash   = source_proceeds - target_cost       (>= 0)
cash_after      = cash_before + residual_cash
```

If `target_cost > source_proceeds` due to an unexpected rounding path, the implementation must reduce `target_units` by one unit quantum (0.001) until `target_cost <= source_proceeds`. It must never post a negative residual.

### 3.6 SIP

- Contribution amount is the external flow and is posted exactly as instructed.
- Purchase uses the same ROUND_DOWN rule as a standalone purchase.
- Any residual remains in cash.
- The external flow is not reduced by the purchase residual.

### 3.7 Reconciliation

Every internal movement must satisfy:

```
cash_effect + unit_value_at_transaction_nav = rounding_residual
```

where `unit_value_at_transaction_nav = units × allotment_nav` before amount rounding. The pipeline reports the sum of residuals by account and transaction type. It never silently discards a difference.

### 3.8 Worked switch residual fixture

- Redeem `100.000` units of scheme A at NAV `20.0000`: `source_proceeds = 100.000 × 20.0000 = 2,000.00`.
- Target scheme B NAV `30.0000`.
- ROUND_HALF_UP would give `2,000 / 30 = 66.666666... → 66.667` units; target cost `66.667 × 30 = 2,000.01`, a negative residual of `-0.01`. This is why the target leg uses ROUND_DOWN.
- ROUND_DOWN gives `66.666` units; target cost `66.666 × 30 = 1,999.98`; residual cash `2,000.00 - 1,999.98 = 0.02`.
- Result: source units down 100.000, target units up 66.666, cash up 0.02. No external flow.

---

## 4. Valuation and stale NAV

### 4.1 Formula

```
position_value = quantize(units × NAV, 2, ROUND_HALF_UP)
portfolio_value = sum(position_value) + cash
```

Cash is already 2 dp. Position values are quantized before summing so the reported total ties exactly to the reported holdings. The unrounded product is retained in the audit calculation where needed.

### 4.2 NAV selection

- If the valuation date has a NAV for the scheme, use it.
- If not, use the latest NAV on or before the valuation date, provided it is within **5 calendar days**.
- If the carried-forward NAV is used, mark the position `stale_nav = true`, record the NAV date and the age in calendar days, and report it separately.
- If the latest NAV is more than 5 calendar days old, valuation fails explicitly for that scheme. No silent forward-fill beyond the limit.
- If no NAV exists at all, valuation fails explicitly.

### 4.3 Valuation fixture

- Cash after purchase: `90,000.00`.
- Holding: `200.000` units; NAV on 2026-01-31: `52.0000`.
- Position value: `200.000 × 52.0000 = 10,400.00`.
- Portfolio value: `90,000.00 + 10,400.00 = 100,400.00`.

### 4.4 Stale NAV fixture

- Valuation date `2026-03-31`; latest NAV `2026-03-27`: age `4` calendar days. Use it; `stale_nav = true`.
- Valuation date `2026-03-31`; latest NAV `2026-03-20`: age `11` calendar days. Valuation fails with `STALE_NAV_LIMIT_EXCEEDED`.
- A weekend or holiday with no NAV is handled by the same rule; it is not silently assumed to be a market day.

---

## 5. Time-weighted return (TWR)

### 5.1 Formula

External flows are at the **start of day**. For a day `t` with an external flow:

```
r_t = (V_t - V_(t-1) - CF_t) / (V_(t-1) + CF_t)
```

For a subperiod with no external flow:

```
r_t = V_end / V_start - 1
```

Then:

```
TWR = product(1 + r_t) - 1
```

If `V_(t-1) + CF_t <= 0`, the subperiod return is undefined; return `INVALID_DENOMINATOR`. Negative cash and negative units are rejected by the ledger, so this should only arise from malformed input.

### 5.2 Subperiod construction

- Start with `V_S`, the value at the start of `S` before any flow.
- For each external flow date `d` in `[S, E]`, use `V_(d-1)` as the pre-flow value, apply the flow at the start of `d`, and compute the day return with the formula above.
- Between flow dates, compute the ratio of end values.
- End with `V_E`.
- If there are no external flows, TWR reduces to `V_E / V_S - 1`.

### 5.3 Zero-flow fixture

`V_S = 100,000.00`, `V_E = 105,000.00`, no flows:

```
TWR = 105,000 / 100,000 - 1 = 0.05 = 5.0000%
```

### 5.4 Contribution fixture (completed by M0 amendment)

- Period under the inclusive full-calendar-day convention: `S = 2026-01-01 00:00`, `E = 2026-02-01 00:00` (midnight immediately after `end_date` 2026-01-31).
- Opening value: `V_S = 100,000.00` at `S`, before any flow.
- Flow: contribution `+20,000.00` at start of day on `2026-01-01` (timestamp `S`); portfolio-perspective sign positive.
- Closing value: `V_E = 122,000.00` at `E`.

```
r = (V_E - V_S - CF) / (V_S + CF)
  = (122,000 - 100,000 - 20,000) / (100,000 + 20,000)
  = 2,000 / 120,000
  = 0.0166666667 = 1.6667%
```

- TWR = `1.6667%`. Modified Dietz: `T = (E - S).days = 31`, flow at `t = 0`, `w = 1`; `R = (122,000 - 100,000 - 20,000) / (100,000 + 1 × 20,000) = 2,000/120,000 = 1.6667%`.

The contribution itself is neutralised; the 2,000 gain is measured against the 120,000 invested.

### 5.5 Withdrawal fixture (completed by M0 amendment)

- Period under the inclusive full-calendar-day convention: `S = 2026-01-01 00:00`, `E = 2026-02-01 00:00`.
- Opening value: `V_S = 100,000.00` at `S`.
- Flow: withdrawal `-20,000.00` at start of day on `2026-01-01` (timestamp `S`); portfolio-perspective sign negative.
- Closing value: `V_E = 82,000.00` at `E`.

```
r = (V_E - V_S - CF) / (V_S + CF)
  = (82,000 - 100,000 - (-20,000)) / (100,000 + (-20,000))
  = 2,000 / 80,000
  = 0.025 = 2.5000%
```

- TWR = `2.5000%`. Modified Dietz with `T = 31`, flow at `t = 0`, `w = 1`; `R = 2,000/80,000 = 2.5000%`.

### 5.6 Same-day flow fixture

`S = 2026-02-10 00:00`, `E = 2026-02-11 00:00` (midnight immediately after `end_date` 2026-02-10); `T = 1`. `V_S = 100,000.00`; contribution `+10,000.00` at start (timestamp `S`); `V_E = 111,000.00` at `E`:

```
r = (111,000 - 100,000 - 10,000) / (100,000 + 10,000)
  = 1,000 / 110,000
  = 0.0090909091 = 0.9091%
```

### 5.7 Mid-period flow fixture

`S = 2026-02-02`, `E = 2026-02-28` (`T = 27` calendar days inclusive).

- `V_S = 100,000.00`.
- Contribution `+50,000.00` on `2026-02-26` at start of day.
- Pre-flow value at the start of 2026-02-26: `102,000.00`.
- Post-flow value: `152,000.00`.
- `V_E = 154,000.00`.

Subperiods:

```
r1 = 102,000 / 100,000 - 1 = 0.02 = 2.0000%
r2 (flow day) = (152,000 - 102,000 - 50,000) / (102,000 + 50,000) = 0
r3 = 154,000 / 152,000 - 1 = 0.0131578947 = 1.3158%
TWR = (1.02)(1.00)(1.0131578947) - 1 = 0.0334210526 = 3.3421%
```

---

## 6. Modified Dietz

### 6.1 Formula

```
R = (V_E - V_S - sum(CF_i)) / (V_S + sum(w_i × CF_i))
w_i = (T - t_i) / T
T = (E - S).days
t_i = (d_i - S).days
```

Flows are at the start of day. `V_S` is before any flow on `S`; `V_E` is after all flows and market movement on `E`.

If the denominator is `<= 0`, return `INVALID_DENOMINATOR`.

### 6.2 Same fixture as 5.7

`T = 27`; flow on 2026-02-26 gives `t = 24`; `w = (27 - 24) / 27 = 3/27 = 0.1111111111`.

```
R = (154,000 - 100,000 - 50,000) / (100,000 + 0.1111111111 × 50,000)
  = 4,000 / 105,555.5556
  = 0.0378947368 = 3.7895%
```

TWR is `3.3421%`; Modified Dietz is `3.7895%`; the difference is `44.74 bp`. The approximation assumes the flow was invested for 3/27 of the period; TWR uses the actual pre-flow valuation to measure the 2% gain before the flow. This is a methodological difference, not an arithmetic error.

### 6.3 Zero-flow and same-day fixtures

- Zero flow: `V_S = 100,000`, `V_E = 105,000`, `T` arbitrary, `R = 5.0000%`.
- Same-day flow: `S = 2026-02-10 00:00`, `E = 2026-02-11 00:00` (midnight immediately after `end_date` 2026-02-10), `T = 1`, `t = 0`, `w = 1`, `R` equals the TWR day result `0.9091%`.

---

## 7. XIRR

### 7.1 Formula and signs

Solve for the annualised rate `r`:

```
sum(CF_i / (1 + r)^((d_i - d_0) / 365)) = 0
```

Investor perspective:

- contributions are **negative**;
- withdrawals are **positive**;
- the terminal portfolio value is a **positive** final cash flow on the period end date.

Purchases, redemptions and switches are internal and are not included. The terminal value is included exactly once. If a withdrawal occurs on the end date, both the withdrawal and the terminal value are included; the terminal value is the value **after** the withdrawal.

Day count: actual/365. `d_0` is the earliest cash-flow date. The mathematical domain is `r > -1`; the configured solver domain is `r ∈ (-0.999999, 1000)` and is recorded with every result.

### 7.2 Simple fixture

- `-100,000.00` on 2026-01-01.
- `+110,000.00` on 2027-01-01 (365 days later).
- `-100,000 + 110,000/(1+r) = 0` gives `r = 0.10 = 10.0000%`.

### 7.3 TWR vs XIRR fixture (F7, exact dates)

Cash flows and portfolio values for the exact annual dates `2025-01-01`, `2026-01-01` and `2027-01-01`:

- `t0 = 2025-01-01`: contribution `-1,000.00`; portfolio value `V_t0 = 1,000.00`.
- `t1 = 2026-01-01`: pre-flow value `V = 1,100.00` (10% gain); contribution `-1,000.00`; post-flow value `V = 2,100.00`.
- `t2 = 2027-01-01`: terminal value `+2,200.00`; `V_t2 = 2,200.00`.

TWR:

```
TWR = (1,100/1,000) × (2,200/2,100) - 1
    = 1.10 × 1.0476190476 - 1
    = 0.1523809524 = 15.2381%
```

XIRR with the full cash-flow table:

| Date | Cash flow |
|---|---:|
| 2025-01-01 | -1,000.00 |
| 2026-01-01 | -1,000.00 |
| 2027-01-01 | +2,200.00 |

```
-1,000 - 1,000/(1+r) + 2,200/(1+r)^2 = 0
Let y = 1+r: 1,000y^2 + 1,000y - 2,200 = 0
y = (-1 + sqrt(9.8)) / 2 = 1.0652475842
r = 0.0652475842 = 6.5248%
```

XIRR = `6.5248%` (annualised, actual/365; each interval is 365 days). TWR = `15.2381%` (period, time-weighted). The difference is expected and must not be presented as an error.

TWR is `15.2381%` (period, time-weighted); XIRR is `6.5248%` (annualised, money-weighted). The difference is because the second contribution received only one year of the two-year performance. They answer different questions and must not be presented as the same number.

### 7.4 Multiple-root fixture

Cash flows: `-100` at year 0, `+230` at year 1, `-132` at year 2.

```
-100 + 230/(1+r) - 132/(1+r)^2 = 0
Let x = 1/(1+r): 132x^2 - 230x + 100 = 0
x = (230 ± sqrt(230^2 - 4×132×100)) / (2×132)
  = (230 ± 10) / 264
x = 0.9090909091 or 0.8333333333
r = 0.10 or 0.20  (10% or 20%)
```

Both roots are valid. The result status must be `MULTIPLE_ROOTS` and both rates must be reported. The solver must not silently choose 10% or 20%.

### 7.5 No-root fixtures

#### 7.5.1 Proven no root

Cash flows: `-100` at year 0, `+1` at year 1, `-100` at year 2.

```
NPV(x) = -100 + x - 100x^2, where x = 1/(1+r)
Maximum at x = 0.005: NPV = -100 + 0.005 - 0.0025 = -99.9975 < 0
```

The quadratic is strictly negative for every real `x`; therefore no positive `x` root exists, and no root exists in the domain. Status: `NO_ROOT_PROVEN`, with the analytic proof recorded.

#### 7.5.2 No root in the configured domain

Cash flows: `-100` at year 0, `+100,200` at year 1.

```
-100 + 100,200/(1+r) = 0
1+r = 1,002
r = 1,001 = 100,100%
```

The only mathematical root is `r = 1,001`, which is outside the configured domain `r ∈ (-0.999999, 1000)`. The scan finds no root. Status: `NO_ROOT_IN_DOMAIN`, with `nearest_root_outside_domain = 1,001` and the search domain/grid recorded. This is not a proof that no mathematical root exists; it is a statement about the configured search.

Do not use a single `NO_ROOT` status for both cases.

### 7.6 Invalid-cash-flow fixture

- `-100` at year 0 only: fewer than two flows and no sign change. Status: `INVALID_CASH_FLOWS`.
- `-100`, `-50`: all negative. Status: `INVALID_CASH_FLOWS`.

### 7.7 Solver design

1. **Validate** cash flows:
   - at least two flows;
   - at least one positive and one negative;
   - valid dates, sorted;
   - `d_0` is the earliest date;
   - duplicate dates are allowed and summed.
   - Otherwise return `INVALID_CASH_FLOWS`.
2. **Domain:** `r ∈ (-0.999999, 1000)`; use `u = ln(1+r)` for a uniform grid.
3. **Root scan:** evaluate NPV on 2,001 grid points. Detect sign changes. Also detect grid points where `|NPV|` is within tolerance at a local minimum, to catch tangential roots.
4. **No bracket:** return `NO_ROOT_PROVEN` only if a documented analytic argument proves there is no root in the domain; otherwise return `NO_ROOT_IN_DOMAIN`, record the search domain, grid resolution and any nearest root outside the domain. Never present a finite scan as proof.
5. **Multiple brackets:** refine each with bisection; if more than one distinct root, `MULTIPLE_ROOTS` with the roots. Do not choose one.
6. **One bracket:** try Newton-Raphson from the bracket midpoint. If Newton leaves the domain, fails or converges outside the bracket, use bounded bisection. If it converges, `SUCCESS`; otherwise `NON_CONVERGENCE`.
7. **Tolerance:** `abs(NPV) <= 1e-8 × max(1, sum(abs(CF)))`; rate tolerance `1e-12`; maximum 200 iterations.
8. **Record:** status, rate(s), iterations, method (`newton`, `bisection`, `scan`), residual, reason, search domain and grid resolution. For `NO_ROOT_IN_DOMAIN`, record the nearest root outside the domain if one is known.
9. **Limitation:** a sign-change scan can miss an even-multiplicity tangential root; the local-minimum check reduces but does not eliminate this risk. The configured domain excludes roots below `-0.999999` or above `1000`. Report these limitations; do not claim universal root detection or mathematical no-root proof from a scan alone.

All arithmetic uses `Decimal`; fractional powers use `exp(exponent × ln(1+r))` with a high-precision context.

---

## 8. SIP fixture

Monthly SIP contribution `5,000.00` on 2026-03-05. The scheme has no NAV on 2026-03-05; the next NAV is 2026-03-06 at `25.0000`.

- Contribution leg: `+5,000.00` cash on 2026-03-05. External flow `+5,000.00`.
- Purchase leg: allotment date 2026-03-06; `units = round_down(5,000 / 25, 3) = 200.000`; `actual_cash = 5,000.00`; residual `0.00`.
- Cash between 2026-03-05 and 2026-03-06 includes the 5,000.00 and is valued.
- TWR counts the 5,000.00 contribution exactly once; the purchase is internal.
- If no NAV exists within 5 calendar days, the whole SIP instalment group is rejected.

### 8.1 SIP valuation and TWR working

Add an opening balance so the interim cash is visible:

- 2026-03-01: opening `CONTRIBUTION` `10,000.00`; cash `10,000.00`.
- 2026-03-05: SIP contribution `+5,000.00`; cash `15,000.00`. External flow `+5,000.00`.
- 2026-03-06: purchase `5,000.00` at NAV `25.0000`; units `200.000`; cash `10,000.00`. Internal, not an external flow.
- 2026-03-31: NAV `27.0000`; position value `200.000 × 27.0000 = 5,400.00`; total value `10,000.00 + 5,400.00 = 15,400.00`.

TWR for 2026-03-01 to 2026-03-31:

```
V_S = 10,000.00
CF on 2026-03-05 = +5,000.00
pre-flow value on 2026-03-05 = 10,000.00
post-flow value = 15,000.00
V_E = 15,400.00

r1 (03-01 to 03-04) = 10,000 / 10,000 - 1 = 0
r2 (03-05, flow day) = (15,000 - 10,000 - 5,000) / (10,000 + 5,000) = 0
r3 (03-06 to 03-31) = 15,400 / 15,000 - 1 = 0.0266666667
TWR = (1.00)(1.00)(1.0266666667) - 1 = 2.6667%
```

Modified Dietz for the same period:

```
T = 31 calendar days inclusive
t = (2026-03-05 - 2026-03-01).days = 4
w = (31 - 4) / 31 = 27/31 = 0.8709677419
R = (15,400 - 10,000 - 5,000) / (10,000 + 0.8709677419 × 5,000)
  = 400 / 14,354.8387097
  = 0.0278651685 = 2.7865%
```

The `11.98 bp` difference is the Modified Dietz approximation, not a cash error. The SIP contribution is counted once; the purchase is internal. If the purchase cannot be priced within five calendar days, the contribution and purchase group is rejected and no dangling cash is left behind.

---

## 9. Correction and restatement fixture (K1/K2)

### 9.1 Opening state

- 2026-01-01: `CONTRIBUTION` of `100,000.00`; cash `100,000.00`.
- 2026-01-10: `PURCHASE` instructed `10,000.00` at NAV `50.0000`; units `200.000`; actual cash `10,000.00`; cash `90,000.00`.
- 2026-01-31: NAV `52.0000`.
- Valuation: `90,000.00 + 200.000 × 52.0000 = 100,400.00`.

### 9.2 K1 report

Generated at `K1 = 2026-01-31 09:00:00+00:00`, period 2026-01-01 to 2026-01-31.

```
V_S = 0.00 before the opening contribution
CF_S = +100,000.00
V_E = 100,400.00
TWR = (100,400 - 0 - 100,000) / (0 + 100,000) = 0.004 = 0.4000%
Modified Dietz = (100,400 - 0 - 100,000) / (0 + 1 × 100,000) = 0.4000%
XIRR: -100,000 at 2026-01-01 00:00, +100,400 at 2026-02-01 00:00 (midnight immediately after end_date 2026-01-31, per the inclusive full-calendar-day convention)
     = -100,000 + 100,400/(1+r)^(31/365) = 0
     → (1+r)^(365/31) = 100,400/100,000 = 1.004
     → (1+r) = 1.004^(365/31) = 1.048125
     → XIRR = 0.048125 = 4.8125%
```

### 9.3 K2 correction

Recorded at `K2 = 2026-02-05 11:00:00+00:00`, effective 2026-01-10:

- Correct the purchase amount from `10,000.00` to `12,000.00`.
- New units: `12,000 / 50.0000 = 240.000`.
- New cash: `100,000.00 - 12,000.00 = 88,000.00`.
- Valuation at 2026-01-31: `88,000.00 + 240.000 × 52.0000 = 100,480.00`.

### 9.4 K2 restated report

```
V_S = 0.00
CF_S = +100,000.00
V_E = 100,480.00
TWR = 0.0048 = 0.4800%
Modified Dietz = 0.4800%
XIRR = -100,000 + 100,480/(1+r)^(31/365) = 0
     → (1+r)^(365/31) = 100,480/100,000 = 1.0048
     → (1+r) = 1.0048^(365/31) = 1.0580006
     → XIRR = 0.0580006 = 5.8001%
```

### 9.5 Restatement deltas

| Figure | K1 | K2 | Delta | Basis points |
|---|---:|---:|---:|---:|
| Cash at 2026-01-31 | 90,000.00 | 88,000.00 | -2,000.00 | — |
| Units | 200.000 | 240.000 | +40.000 | — |
| Portfolio value | 100,400.00 | 100,480.00 | +80.00 | — |
| TWR | 0.4000% | 0.4800% | +0.0800 pp | +8.00 bp |
| Modified Dietz | 0.4000% | 0.4800% | +0.0800 pp | +8.00 bp |
| XIRR | 4.8125% | 5.8001% | +0.9876 pp | +98.76 bp |

Attribution: the changed revision is the 2026-01-10 purchase, correction type `REPLACE`, reason code `AMOUNT_CORRECTION`, synthetic operator and source reference stored in the correction group. The K1 query must still return `200.000` units, cash `90,000.00`, value `100,400.00`, TWR `0.4000%` and XIRR `4.8125%`.

### 9.6 Invalid correction fixture

- Purchase `100.000` units on 2026-01-10.
- Redeem `80.000` units on 2026-01-20; remaining `20.000`.
- Correction recorded 2026-02-01, effective 2026-01-10, changes the purchase to `50.000` units.
- After the correction, the 2026-01-20 redemption would leave `-30.000` units.
- The correction is rejected with reason `NEGATIVE_UNITS_DOWNSTREAM`; balances and reports do not change.

---

## 10. Report snapshots and replay

### 10.1 Snapshot metadata

A report snapshot stores:

- `snapshot_id`;
- `account_id`, `period_start`, `period_end`;
- `known_as_of` (UTC);
- `generated_at` (simulated UTC);
- `calculation_engine_version`;
- `git_commit_sha` and `git_dirty`;
- `schema_migrations_hash`;
- `nav_snapshot_id` and `nav_snapshot_checksum`;
- `scheme_mapping_version`;
- `config_hash` (generator, rounding, sensitivity where relevant);
- `rounding_policy`;
- `canonical_payload` (JSONB);
- `payload_sha256`;
- `created_at` (wall-clock audit only).

### 10.2 Canonical payload

- Sorted keys.
- Decimal values as strings with fixed precision.
- Dates as ISO `YYYY-MM-DD`.
- Timestamps as ISO UTC.
- Explicit `null` for unavailable values.
- No binary floats.
- Include cash, positions (scheme code, name, units, NAV, NAV date, stale flag, value), total value, external flows, TWR, Modified Dietz, XIRR result and warnings.
- Exclude wall-clock audit fields and `generated_at` from the economic hash, or store and reuse them; the choice must be consistent and documented.

### 10.3 Retrieval vs replay vs restatement

| Operation | What it does | Guarantee |
|---|---|---|
| **Archived retrieval** | Returns the stored canonical payload by `snapshot_id`. | Always exact; no recalculation. |
| **Replay** | Recalculates from the stored period, `known_as_of`, NAV snapshot, engine/schema/config versions and rounding policy; compares canonical payload and hash. | Exact for the same engine version and immutable NAV snapshot. If the engine version differs, return `ENGINE_VERSION_MISMATCH`; the archived payload is still retrievable. |
| **Restatement** | Recalculates with a later `known_as_of` and compares with the original. | Produces a new report and attribution; does not overwrite the original. |

### 10.4 Overwrite-in-place comparator

The comparator schema stores only current transaction rows (no revision history, no prior payload, no archived report). It is fed the same transaction stream and corrections. It attempts to reconstruct the original K1 report from its retained data. For a corrected account it cannot recover the prior instruction amount, derived units, cash leg, revision lineage, reason or prior payload, so the reconstruction fails or differs. The evaluation reports how many historical reports remain reproducible (expected: only unaffected accounts) and exactly what is lost. It must not retrieve a snapshot it previously saved.

### 10.5 Replay fixture with a changed NAV snapshot, engine version, or updated inputs

Use the K1 snapshot from section 9.2, under the inclusive full-calendar-day convention:

- K1 `known_as_of` = 2026-01-31 09:00:00+00:00;
- Period `S = 2026-01-01 00:00`, `E = 2026-02-01 00:00`;
- NAV snapshot `V1` has 2026-01-31 NAV `52.0000`;
- K1 payload: 200.000 units, cash 90,000.00, value 100,400.00, TWR 0.4000%, XIRR 4.8125%;
- `payload_sha256 = H1` (the concrete digest is generated in the M5 fixture test; no digest is invented here).

The fixture separates four distinct outcomes:

| Case | Operation / input | Status | Working / expected |
|---|---|---|---|
| R1 | Exact historical replay: same engine version, same NAV snapshot `V1`, same mapping/config/rounding | `REPLAY_EXACT` | Recompute from stored K1 metadata; payload and `H1` identical; archived retrieval exact. |
| R2 | Input mismatch: same engine version, NAV snapshot `V2` with 2026-01-31 NAV `52.5000` | `NAV_SNAPSHOT_MISMATCH` | Value `90,000.00 + 200.000 × 52.5000 = 100,500.00`; TWR `(100,500 - 100,000)/100,000 = 0.5000%`; XIRR `(100,500/100,000)^(365/31) - 1 = 6.0483%`; payload and hash differ from K1; archived retrieval still returns 100,400.00, 0.4000% and 4.8125%. |
| R3 | Engine version mismatch: engine `1.1.0` instead of `1.0.0`, NAV snapshot `V1` unchanged | `ENGINE_VERSION_MISMATCH` | Replay is not accepted as comparable; no numeric equality claim; archived K1 payload remains retrievable exactly. |
| R4 | Restatement generation with updated inputs: K2 correction (purchase amount `12,000.00` effective 2026-01-10, `known_as_of` 2026-02-05) | `RESTATEMENT_GENERATED` | Recalculate with the later `known_as_of` and updated inputs; produce K2 report (value 100,480.00, TWR 0.4800%, XIRR 5.8001%); K1 archived retrieval remains exact; K2 vs K1 delta attributed to the purchase revision. |

The replay must not silently substitute the latest NAV or the latest engine. A changed market-data snapshot or engine version is a different reconstruction and must be labelled as such; a restatement with updated inputs is a separate generation from an exact historical replay.

---

## 11. Restatement attribution

For each changed figure:

1. Compute the K1 and K2 canonical payloads.
2. Identify changed fields.
3. Identify the set of transaction revisions that differ between K1 and K2 and are effective within the period or valuation date.
4. Store original value, restated value, delta and basis points where applicable.
5. Link the change to each changed revision's correction type, reason code and note.
6. If exactly one revision explains the change, mark it `SINGLE_REVISION`.
7. If multiple revisions contribute, mark `MULTI_REVISION` and list all of them. For cash, units and valuation, exact per-revision counterfactual deltas may be computed. For nonlinear performance measures, the attribution is a linked explanation, not a claim of additive decomposition.
8. If no revision explains a change, mark `UNEXPLAINED` and fail the attribution invariant; do not hide it.

The worked K1/K2 fixture in section 9 is a `SINGLE_REVISION` example.

---

## 12. Sensitivity statistics

### 12.1 Definitions

For a scenario `s`, path `p` and window `w`:

```
correct_return = measure(correct_history)
error_return   = measure(scenario_history)
signed_change_bp = (error_return - correct_return) × 10,000
absolute_change_bp = abs(signed_change_bp)
```

Report, per scenario and measure:

- `n`: number of valid paths/windows;
- median signed change in bp;
- median absolute change in bp;
- 95th percentile absolute change in bp;
- share of observations with absolute change above each configured threshold (for example 5, 10, 25, 50, 100 bp);
- count of failed/insufficient paths and the reason.

Do not let positive and negative errors cancel and conceal magnitude: the signed median is reported **alongside** the median absolute and p95 absolute.

### 12.2 Percentile method

Use a deterministic method: sort the values; for `p` in `[0,100]`, use linear interpolation between the two nearest order statistics. Document the method in the generated results. The same method is used in tests and the dashboard.

### 12.3 Interpretation limits

- The correction magnitudes are generator-controlled scenarios, not observed real-world error rates.
- The study measures sensitivity of reported returns to controlled errors; it does not measure user benefit, client outcomes, investment performance or regulatory compliance.
- All pre-registered scenarios are reported with n. Do not cherry-pick.
- A null or inconclusive result is a valid result and must be reported.

### 12.4 Pre-registered study (draft; freeze before running)

`config/sensitivity.yaml` is the pre-registration. The current draft is marked `draft_pending_freeze`; it must be frozen and hashed before the study runs. It defines:

- Direct-Growth path eligibility and seeded sample cap;
- fixed 12-month windows at quarter starts;
- deterministic monthly SIP amount and day rule;
- backdating, mis-sizing and missed-correction scenarios;
- basis-point thresholds;
- signed median, median absolute, p95 absolute and threshold shares.

---

## 13. Fixture summary

| ID | Fixture | Key result |
|---|---|---|
| F1 | Purchase and valuation | 200.000 units; cash 90,000.00; value 100,400.00 |
| F2 | TWR vs Modified Dietz with mid-period flow | TWR 3.3421%; MD 3.7895%; 44.74 bp difference |
| F3 | Zero-flow period | TWR = MD = 5.0000% |
| F4 | Same-day contribution | TWR = MD = 0.9091% |
| F5 | Contribution / withdrawal | 1.6667% / 2.5000%; period 2026-01-01 to 2026-02-01, flows at start of period |
| F6 | Simple XIRR | 10.0000% |
| F7 | TWR vs XIRR with two contributions | TWR 15.2381%; XIRR 6.5248%; dates 2025-01-01, 2026-01-01, 2027-01-01 |
| F8 | XIRR multiple roots | 10% and 20%; `MULTIPLE_ROOTS` |
| F9 | XIRR no root, proven | `NO_ROOT_PROVEN` for -100, +1, -100 |
| F10 | XIRR invalid flows | `INVALID_CASH_FLOWS` |
| F11 | Switch residual | 66.666 target units; 0.02 residual cash |
| F12 | Stale NAV | 4 days stale; 11 days fails |
| F13 | K1/K2 correction | TWR 0.4000% → 0.4800%; XIRR 4.8125% → 5.8001% |
| F14 | Invalid correction | `NEGATIVE_UNITS_DOWNSTREAM` rejection |
| F15 | Delayed purchase/allotment date | No posting on instruction date; cash and 400.000 units post together on the next NAV date |
| F16 | Same-day posting sequence and insufficient cash | Withdrawal at sequence 10 rejected; contribution at 20; purchase at 30 succeeds; final 120.000 units and 300.00 cash |
| F17 | SIP contribution and purchase on different dates | Cash 15,000.00 on 03-05; 200.000 units and 10,000.00 cash on 03-06; TWR 2.6667%; MD 2.7865% |
| F18 | XIRR no root in configured domain | Root at 1,001 is outside the domain; `NO_ROOT_IN_DOMAIN` |
| F19 | Replay with changed NAV snapshot, engine version or updated inputs | R1 `REPLAY_EXACT`; R2 `NAV_SNAPSHOT_MISMATCH`; R3 `ENGINE_VERSION_MISMATCH`; R4 `RESTATEMENT_GENERATED`; archived K1 exact |

Every fixture must be implemented as a test that does **not** call the production function for its expected value.

---

## Appendix A — Fixture working papers

This appendix is the review sheet for M0. It gives the inputs, the independent working and the expected output. Detailed formulas are in the referenced sections.

### A.1 F1 — Purchase and valuation

- Inputs: contribution 100,000.00; purchase 10,000.00 at NAV 50.0000; 2026-01-31 NAV 52.0000.
- Working: units = 10,000 / 50 = 200.000; cash = 100,000 - 10,000 = 90,000.00; value = 90,000 + 200 × 52 = 100,400.00.
- Expected: units 200.000; cash 90,000.00; value 100,400.00.

### A.2 F2 — TWR vs Modified Dietz, mid-period flow

- Inputs: `V_S` 100,000.00; flow +50,000.00 on 2026-02-26; pre-flow 102,000.00; post-flow 152,000.00; `V_E` 154,000.00; `T` 27; `t` 24.
- Working: TWR = (102,000/100,000)(154,000/152,000) - 1 = 3.3421%; MD = 4,000 / (100,000 + (3/27)50,000) = 3.7895%.
- Expected: TWR 3.3421%; MD 3.7895%; difference 44.74 bp.

### A.3 F3 — Zero-flow period

- Inputs: `V_S` 100,000.00; `V_E` 105,000.00; no flows.
- Working: 105,000/100,000 - 1.
- Expected: TWR = MD = 5.0000%.

### A.4 F4 — Same-day contribution

- Inputs: `S = 2026-02-10 00:00`, `E = 2026-02-11 00:00` (midnight immediately after `end_date` 2026-02-10); `V_S` 100,000.00; flow +10,000.00; `V_E` 111,000.00.
- Working: (111,000 - 100,000 - 10,000)/(100,000 + 10,000) = 1,000/110,000.
- Expected: TWR = MD = 0.9091%.

### A.5 F5 — Contribution and withdrawal (completed)

- Inputs: contribution case `V_S` 100,000.00, flow +20,000.00 on 2026-01-01, `V_E` 122,000.00; withdrawal case flow -20,000.00 on 2026-01-01, `V_E` 82,000.00. Period under the inclusive full-calendar-day convention: `S = 2026-01-01 00:00`, `E = 2026-02-01 00:00`.
- Working: contribution `(122,000 - 100,000 - 20,000)/(100,000 + 20,000) = 2,000/120,000 = 1.6667%`; withdrawal `(82,000 - 100,000 - (-20,000))/(100,000 + (-20,000)) = 2,000/80,000 = 2.5000%`.
- Expected: 1.6667% and 2.5000%.

### A.6 F6 — Simple XIRR

- Inputs: -100,000.00 on 2026-01-01; +110,000.00 on 2027-01-01 (365 days).
- Working: -100,000 + 110,000/(1+r) = 0.
- Expected: 10.0000%, `SUCCESS`.

### A.7 F7 — TWR vs XIRR, two contributions (exact dates)

- Inputs: cash flows -1,000.00 at 2025-01-01, -1,000.00 at 2026-01-01, +2,200.00 at 2027-01-01; pre-flow value at 2026-01-01 = 1,100.00; post-flow = 2,100.00; terminal value = 2,200.00.
- Working: TWR = (1,100/1,000)×(2,200/2,100) - 1 = 15.2381%; XIRR solves -1,000 - 1,000/(1+r) + 2,200/(1+r)^2 = 0.
- Expected: TWR 15.2381%; XIRR 6.5248%; dates 2025-01-01, 2026-01-01, 2027-01-01.

### A.8 F8 — XIRR multiple roots

- Inputs: -100 at year 0; +230 at year 1; -132 at year 2.
- Working: 132x^2 - 230x + 100 = 0, x = 1/(1+r); roots x = 0.9090909 and 0.8333333.
- Expected: r = 10% and 20%; `MULTIPLE_ROOTS`; no single XIRR chosen.

### A.9 F9 — XIRR no root, proven

- Inputs: -100 at year 0; +1 at year 1; -100 at year 2.
- Working: NPV(x) = -100 + x - 100x^2; maximum at x = 0.005 is -99.9975 < 0.
- Expected: `NO_ROOT_PROVEN`; analytic proof recorded.

### A.10 F10 — XIRR invalid flows

- Inputs: single -100; or -100 and -50.
- Working: fewer than two flows, or no positive/negative sign change.
- Expected: `INVALID_CASH_FLOWS`.

### A.11 F11 — Switch residual

- Inputs: 100.000 source units at NAV 20.0000; target NAV 30.0000.
- Working: proceeds 2,000.00; target units ROUND_DOWN(2,000/30, 3) = 66.666; target cost 1,999.98; residual 0.02.
- Expected: source units down 100.000; target units up 66.666; cash up 0.02; no external flow.

### A.12 F12 — Stale NAV

- Inputs: valuation 2026-03-31; latest NAV 2026-03-27 (4 days); latest NAV 2026-03-20 (11 days).
- Working: age = valuation date - NAV date.
- Expected: 4 days uses NAV and flags stale; 11 days fails `STALE_NAV_LIMIT_EXCEEDED`.

### A.13 F13 — K1/K2 correction

- Inputs: contribution 100,000.00 on 2026-01-01; purchase 10,000.00 at NAV 50.0000 on 2026-01-10; K1 NAV 52.0000; K2 correction to 12,000.00 effective 2026-01-10, recorded 2026-02-05.
- Working: K1 200.000 units, cash 90,000.00, value 100,400.00, TWR 0.4000%, XIRR 4.8125%; K2 240.000 units, cash 88,000.00, value 100,480.00, TWR 0.4800%, XIRR 5.8001%.
- Expected: K1 unchanged at K1; K2 restates; delta attributed to the purchase revision.

### A.14 F14 — Invalid correction

- Inputs: 100.000 units purchased 2026-01-10; 80.000 redeemed 2026-01-20; correction effective 2026-01-10 reduces purchase to 50.000.
- Working: corrected balance at 2026-01-20 = 50.000 - 80.000 = -30.000.
- Expected: `NEGATIVE_UNITS_DOWNSTREAM`; correction rejected; balances unchanged.

### A.15 F15 — Delayed purchase/allotment date

- Inputs: contribution 50,000.00 on 2026-01-05; purchase instructed 2026-01-09 for 10,000.00; no NAV on 2026-01-09; next NAV 2026-01-12 at 25.0000.
- Working: instruction date is audit-only; the whole purchase posts on 2026-01-12; units = 10,000/25 = 400.000; cash = 50,000 - 10,000 = 40,000.00; value on 2026-01-12 = 40,000 + 400 × 25 = 50,000.00.
- Expected: no cash or unit posting on 2026-01-09; 400.000 units and 40,000.00 cash on 2026-01-12; no receivable; if no NAV within 5 calendar days, reject `NO_NAV_WITHIN_LIMIT`.

### A.16 F16 — Same-day posting sequence and insufficient cash

- Inputs: opening cash 1,000.00 on 2026-02-10; withdrawal 1,200.00 at `posting_sequence` 10; contribution +500.00 at 20; purchase 1,200.00 at NAV 10.0000 at 30.
- Working:
  - seq 10: cash 1,000.00 - 1,200.00 < 0 → reject `INSUFFICIENT_CASH`, no posting.
  - seq 20: cash 1,000.00 + 500.00 = 1,500.00.
  - seq 30: units = 1,200/10 = 120.000; cash = 1,500.00 - 1,200.00 = 300.00.
- Expected: withdrawal rejected and recorded; 120.000 units; cash 300.00; no negative cash. A contributions-first rule would instead post the withdrawal and reject the purchase, proving the need for explicit `posting_sequence`.

### A.17 F17 — SIP contribution and purchase on different dates

- Inputs: opening contribution 10,000.00 on 2026-03-01; SIP contribution +5,000.00 on 2026-03-05; purchase 5,000.00 at NAV 25.0000 on 2026-03-06; 2026-03-31 NAV 27.0000.
- Working: cash 15,000.00 on 03-05; 200.000 units and 10,000.00 cash on 03-06; value 15,400.00 on 03-31; TWR 2.6667%; MD 2.7865%.
- Expected: contribution counted once as external; purchase internal; interim cash valued; TWR 2.6667%; MD 2.7865%; difference 11.98 bp.

### A.18 F18 — XIRR no root in the configured domain

- Inputs: -100 at year 0; +100,200 at year 1.
- Working: -100 + 100,200/(1+r) = 0 → r = 1,001, outside `(-0.999999, 1000)`.
- Expected: `NO_ROOT_IN_DOMAIN`; `nearest_root_outside_domain = 1,001`; search domain/grid recorded; not `NO_ROOT_PROVEN`.

### A.19 F19 — Replay with changed NAV snapshot, engine version, or updated inputs

The four outcomes are distinct and must not be conflated:

- **R1 — Exact historical replay:** same engine version (1.0.0), same NAV snapshot `V1` (2026-01-31 NAV `52.0000`), same period, same inputs, same rounding policy.
  - Inputs: K1 snapshot from F13; period `S = 2026-01-01 00:00`, `E = 2026-02-01 00:00`; NAV snapshot `V1` (2026-01-31 NAV `52.0000`).
  - Working: recompute from the stored K1 metadata; payload and `payload_sha256 = H1` are identical.
  - Expected: `REPLAY_EXACT`.

- **R2 — Input mismatch (changed NAV snapshot):** same engine version (1.0.0), NAV snapshot `V2` with 2026-01-31 NAV `52.5000`.
  - Working: `V_E = 90,000.00 + 200.000 × 52.5000 = 100,500.00`; TWR `(100,500 - 100,000)/100,000 = 0.5000%`; XIRR `(100,500/100,000)^(365/31) - 1 = 6.0483%` (terminal valuation timestamp is `E = 2026-02-01 00:00`, per the inclusive full-calendar-day convention).
  - Expected: `NAV_SNAPSHOT_MISMATCH`; payload and hash differ from K1; archived retrieval still returns `100,400.00`, TWR `0.4000%`, XIRR `4.8125%`.

- **R3 — Engine version mismatch:** engine `1.1.0` instead of `1.0.0`, NAV snapshot `V1` unchanged.
  - Working: the replay is not accepted as comparable; no numeric equality claim is made.
  - Expected: `ENGINE_VERSION_MISMATCH`; archived K1 payload remains retrievable exactly.

- **R4 — Restatement generation with updated inputs:** K2 correction (purchase amount `12,000.00` effective `2026-01-10`, `known_as_of` `2026-02-05`).
  - Working: recalculate with the later `known_as_of` and the updated inputs; produce the K2 report.
  - Expected: `RESTATEMENT_GENERATED`; K2 report value `100,480.00`, TWR `0.4800%`, XIRR `5.8001%`; K1 archived retrieval remains exact; the K2 vs K1 delta is attributed to the purchase revision.

The exact historical replay (R1) is a reconstruction with immutable inputs; a changed NAV snapshot (R2), a changed engine version (R3) or updated inputs (R4) are separate outcomes and must never be reported as `REPLAY_EXACT`.
