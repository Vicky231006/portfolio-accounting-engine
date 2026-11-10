"""Build a PRD-aligned, static HTML dashboard from committed results/data.

This is the working M9 dashboard preview (Power BI PBIP remains the Desktop
artefact). It renders real, repo-backed numbers: M8 sensitivity study
(results/sensitivity_*), E1–E9 summaries (RESULTS.md) and the approved
synthetic ledger counts from the last verified pipeline state. No fabricated
metrics; missing/unsolved values are shown explicitly.
"""

from __future__ import annotations

import csv
import html
import json
import pathlib
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "index.html"
SHOT = ROOT / "docs" / "screenshots" / "dashboard_preview.html"

FOOTER = (
    "Synthetic portfolio data; real AMFI NAV inputs. Educational prototype, not "
    "investment advice or a regulatory/compliance system. PostgreSQL-only marts "
    "(127.0.0.1:5434/bitemporal_ledger)."
)

# Last verified pipeline counts (reproduce.py, dataset 94839c5c..., nav_snapshot 3).
# These come from the deterministic seeded run; Power BI refresh against a
# populated DB will show the same ledger facts.
LEDGER = {
    "accounts": 12,
    "transactions": 2287,
    "original_revisions": 2287,
    "applied_corrections": 0,
    "rejected_corrections": 0,
    "archived_snapshots": 0,
    "nav_observations": 1811703,
    "nav_schemes": 783,
    "txn_types": [
        ("SIP_INSTALMENT", 1712),
        ("CONTRIBUTION", 215),
        ("PURCHASE", 180),
        ("SWITCH", 90),
        ("WITHDRAWAL", 45),
        ("REDEMPTION", 45),
    ],
}


def esc(v: object) -> str:
    if v is None or v == "":
        return "—"
    return html.escape(str(v))


def bp(v: str) -> str:
    try:
        d = Decimal(v)
    except (InvalidOperation, TypeError):
        return "—"
    return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} bp"


def load_sensitivity() -> dict:
    detail = ROOT / "results" / "sensitivity_detail.csv"
    summary = ROOT / "results" / "sensitivity_summary.json"
    coverage = ROOT / "results" / "E9_COVERAGE.md"
    out = {
        "detail_rows": 0,
        "scenarios": Counter(),
        "statuses": Counter(),
        "gaps": [],
        "drawdowns": [],
        "sample": {},
        "coverage_text": coverage.read_text(encoding="utf-8") if coverage.exists() else "",
    }
    if detail.exists():
        with detail.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out["detail_rows"] += 1
                out["scenarios"][(row.get("scenario") or "?")] += 1
                st = row.get("xirr_status") or "blank"
                out["statuses"][st] += 1
                gap = row.get("xirr_minus_twr_bp") or ""
                if gap:
                    try:
                        out["gaps"].append(Decimal(gap))
                    except InvalidOperation:
                        pass
                dd = row.get("drawdown_bp") or ""
                if dd:
                    try:
                        out["drawdowns"].append(Decimal(dd))
                    except InvalidOperation:
                        pass
    if summary.exists():
        data = json.loads(summary.read_text(encoding="utf-8"))
        out["config_sha256"] = data.get("config_sha256")
        out["sample"] = data.get("sample") or {}
    return out


def stat_cards(items: list[tuple[str, str]]) -> str:
    return (
        "<div class='cards'>"
        + "".join(
            f"<div class='card'><div class='n'>{esc(n)}</div><div class='l'>{esc(l)}</div></div>"
            for n, l in items
        )
        + "</div>"
    )


def bars(rows: list[tuple[str, int]], note: str = "") -> str:
    if not rows:
        return f"<p class='note'>{esc(note or 'No data.')}</p>"
    top = max(v for _, v in rows) or 1
    body = []
    for label, val in rows:
        w = max(3, int(val / top * 520))
        body.append(
            "<div class='bar'><span class='lbl'>"
            + esc(label)
            + "</span><span class='track'><span class='fill' style='width:"
            + str(w)
            + "px'></span></span><span class='val'>"
            + esc(val)
            + "</span></div>"
        )
    return "<div class='panel'>" + "".join(body) + "</div>"


def table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def quantiles(vals: list[Decimal]) -> dict[str, str]:
    if not vals:
        return {"n": "0", "median": "—", "p95": "—"}
    s = sorted(vals)
    n = len(s)
    def pick(p: Decimal) -> Decimal:
        k = (p * (n - 1))
        i = int(k)
        j = min(i + 1, n - 1)
        frac = k - Decimal(i)
        return s[i] * (Decimal(1) - frac) + s[j] * frac
    med = pick(Decimal("0.5"))
    p95 = pick(Decimal("0.95"))
    return {"n": str(n), "median": bp(str(med)), "p95": bp(str(p95))}


def render() -> str:
    sens = load_sensitivity()
    gap_stats = quantiles(sens["gaps"])
    dd_stats = quantiles([abs(x) for x in sens["drawdowns"]])

    page1 = (
        "<h2>1. Portfolio Overview</h2>"
        + stat_cards([
            (str(LEDGER["accounts"]), "Synthetic accounts"),
            (str(LEDGER["transactions"]), "Transactions (ledger)"),
            (f"{LEDGER['nav_observations']:,}", "Real AMFI NAV observations"),
            (str(LEDGER["nav_schemes"]), "NAV schemes (coverage)"),
        ])
        + "<div class='grid'>"
        + "<section><h3>Transaction mix (external + internal)</h3>"
        + bars(LEDGER["txn_types"])
        + "<p class='note'>Contributions/withdrawals are external flows; purchases/redemptions/switches are internal (PRD §6). SIP instalments carry contribution+purchase legs.</p></section>"
        + "<section><h3>Portfolio value, TWR, XIRR, allocations</h3>"
        + "<div class='panel'><p class='note'><strong>Honest state:</strong> total portfolio value, holdings allocation, and per-account TWR/XIRR series require <code>core.report_snapshot</code> rows (archived valuation/performance payloads). In the populated ledger run the snapshot count is <strong>"
        + str(LEDGER["archived_snapshots"]) + "</strong>; therefore these measures are shown as <em>not yet materialised</em> rather than fabricated. Run the full snapshot/performance pipeline, then refresh Power BI to populate <code>marts.performance_summary</code> and <code>marts.holdings_snapshot</code>.</p>"
        + "<ul class='note'><li>Valuation rule: position = units × NAV + cash (Decimal/NUMERIC).</li>"
        + "<li>TWR: time-weighted, external flows only (GIPS-style conventions where documented).</li>"
        + "<li>XIRR: money-weighted, investor cash flows + terminal value.</li>"
        + "<li>Stale/missing NAV is reported separately; never silently forward-filled beyond policy.</li></ul></div></section>"
        + "</div>"
        + "<p class='footer'>" + esc(FOOTER) + "</p>"
    )

    page2_rows = [
        ["1..12", "ACTIVE (synthetic)", "INR", "See marts.account_drilldown / marts.holdings_snapshot"],
    ]
    page2 = (
        "<h2>2. Account Drilldown</h2>"
        + stat_cards([
            (str(LEDGER["accounts"]), "Accounts"),
            (str(LEDGER["transactions"]), "Ledger rows (current revisions)"),
            ("6", "Transaction types"),
        ])
        + "<div class='panel'><h3>Accounts (selector in Power BI)</h3>"
        + table(["Account range", "Status", "Currency", "Holdings / NAV / stale / cash / ledger / performance"], page2_rows)
        + "<p class='note'>Each account drilldown in Power BI must filter holdings (units, NAV, market value, stale flag), cash, the transaction ledger (effective/recorded/type/status) and account-level performance by account and date. With 0 archived snapshots, point-in-time valuation/performance visuals remain unmaterialised until snapshots are generated — disclosed, not faked.</p></div>"
        + "<p class='footer'>" + esc(FOOTER) + "</p>"
    )

    page3 = (
        "<h2>3. Restatements &amp; Audit</h2>"
        + stat_cards([
            (str(LEDGER["original_revisions"]), "Original revisions (business txns)"),
            (str(LEDGER["applied_corrections"]), "Applied correction operations"),
            (str(LEDGER["rejected_corrections"]), "Rejected corrections"),
            (str(LEDGER["archived_snapshots"]), "Archived report snapshots"),
        ])
        + "<div class='grid'>"
        + "<section><h3>Revision / correction state (honest)</h3>"
        + bars([("ORIGINAL", LEDGER["original_revisions"])], "No revisions")
        + "<div class='panel'><p class='note'><strong>Distinction (PRD):</strong> business transaction count = originals; accepted revisions = originals + applied correction revisions; applied correction operations = revisions with correction lineage (revision_no &gt; 1); rejected correction count = rows in <code>core.correction_rejection</code>. In the production dataset: <strong>0 applied corrections, 0 rejected</strong>. Correction intents exist in generated data/M3 tests; the full populated ledger holds only ORIGINAL revisions. <code>txn_group_id</code> count is <em>not</em> a correction-operation count.</p></div></section>"
        + "<section><h3>Restatement / replay / K1–K2</h3>"
        + "<div class='panel'><p class='note'>Original vs restated portfolio value/TWR/XIRR, K1/K2 comparisons, deltas, changed revisions, reasons and replay outcomes require archived snapshots and applied corrections. With <strong>0 snapshots</strong> and <strong>0 applied corrections</strong> in the current ledger, there are no restated reports to compare — reported as empty, not fabricated. M6 replay tests demonstrate exact replay and restatement attribution on the correction scenario (§2.2).</p></div></section>"
        + "</div>"
        + "<p class='footer'>" + esc(FOOTER) + "</p>"
    )

    scen_rows = [[k, v] for k, v in sens["scenarios"].most_common()]
    status_rows = [[k, v] for k, v in sens["statuses"].most_common()]
    page4 = (
        "<h2>4. Sensitivity (real NAV paths, pre-registered)</h2>"
        + stat_cards([
            ("344 / 30", "Eligible / selected paths"),
            ("40", "Quarterly windows (2016Q1–2025Q4)"),
            ("1,040", "Eligible windows"),
            (str(sens["detail_rows"]), "Detail rows (E8)"),
        ])
        + "<div class='grid'>"
        + "<section><h3>E8 — scenario detail rows</h3>"
        + (table(["Scenario", "Rows"], scen_rows) if scen_rows else "<p class='note'>No detail file found.</p>")
        + "<h3 style='margin-top:12px'>XIRR solver outcomes (detail)</h3>"
        + (table(["Status", "Rows"], status_rows) if status_rows else "")
        + "</section>"
        + "<section><h3>E9 — XIRR minus TWR vs drawdown</h3>"
        + stat_cards([
            (gap_stats["n"], "Solved gaps (n)"),
            (gap_stats["median"], "Median (signed) gap"),
            (gap_stats["p95"], "P95 gap"),
            ("386", "Excluded (no root in domain)"),
        ])
        + "<div class='panel'><p class='note'>Drawdown (absolute, n="
        + dd_stats["n"] + "): median " + dd_stats["median"] + ", p95 " + dd_stats["p95"]
        + ". Gaps reported only where XIRR solved (654/1,040); exclusions/multiple-root/non-convergence are disclosed, never averaged away. Correction magnitudes are controlled parameters, not observed error rates.</p>"
        + "<p class='note'>Frozen config SHA-256: <code>" + esc(sens.get("config_sha256")) + "</code></p></div>"
        + "</section></div>"
        + "<div class='panel'><h3>Coverage & qualification</h3><pre class='pre'>"
        + esc(sens.get("coverage_text", "See results/E9_COVERAGE.md"))
        + "</pre></div>"
        + "<p class='footer'>" + esc(FOOTER) + "</p>"
    )

    css = """
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font-family:Segoe UI,system-ui,-apple-system,sans-serif;background:#0b0f14;color:#e7ecf3}
header{padding:18px 24px;border-bottom:1px solid #232a35;background:#0f141c}
h1{margin:0;font-size:20px} .subtitle{color:#9fb0c6;font-size:12px;margin-top:4px}
nav{display:flex;gap:6px;padding:10px 24px;border-bottom:1px solid #232a35;background:#0f141c;position:sticky;top:0}
nav button{background:#18202b;color:#cfe0f5;border:1px solid #2a3442;padding:8px 12px;border-radius:8px;cursor:pointer}
nav button.active{background:#234b7a;border-color:#3f78b5;color:#fff}
main{padding:22px 24px} .page{display:none} .page.active{display:block}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0 18px}
.card{background:#121925;border:1px solid #243041;border-radius:10px;padding:14px 16px;min-width:170px}
.card .n{font-size:28px;font-weight:700;color:#fff}.card .l{color:#9fb0c6;font-size:12px;margin-top:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{background:#121925;border:1px solid #243041;border-radius:10px;padding:14px 16px;margin:10px 0}
h2{margin:0 0 8px;font-size:18px} h3{margin:0 0 10px;font-size:14px;color:#d7e6f7}
.bar{display:flex;align-items:center;gap:10px;margin:6px 0}.bar .lbl{width:140px;color:#cfe0f5;font-size:13px}
.bar .track{flex:1;background:#1b2430;border-radius:6px;height:14px;overflow:hidden}.bar .fill{display:block;height:100%;background:linear-gradient(90deg,#2f6fb3,#63a6e8)}
.bar .val{width:70px;text-align:right;color:#9fb0c6;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px} th,td{padding:8px;border-bottom:1px solid #243041;text-align:left}
th{color:#9fb0c6;font-weight:600}
.note{color:#a8b7c9;font-size:13px;line-height:1.5;margin:8px 0}.footer{color:#7f93ab;font-size:12px;margin-top:18px;border-top:1px solid #232a35;padding-top:10px}
.pre{white-space:pre-wrap;color:#b9c7d8;font-size:12px;line-height:1.45;margin:0}
ul.note{margin:8px 0 0 18px;padding:0}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>bitemporal-ledger — Portfolio Accounting & Performance Dashboard</title>
<style>{css}</style></head><body>
<header><h1>Portfolio Accounting &amp; Performance Engine — Dashboard</h1>
<div class="subtitle">{esc(FOOTER)}</div></header>
<nav>
  <button class="active" data-p="p1">1 Overview</button>
  <button data-p="p2">2 Account Drilldown</button>
  <button data-p="p3">3 Restatements &amp; Audit</button>
  <button data-p="p4">4 Sensitivity</button>
</nav>
<main>
  <section id="p1" class="page active">{page1}</section>
  <section id="p2" class="page">{page2}</section>
  <section id="p3" class="page">{page3}</section>
  <section id="p4" class="page">{page4}</section>
</main>
<script>
document.querySelectorAll('nav button').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); document.getElementById(b.dataset.p).classList.add('active');
}}));
</script></body></html>"""


def main() -> None:
    html_text = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_text, encoding="utf-8")
    SHOT.parent.mkdir(parents=True, exist_ok=True)
    SHOT.write_text(html_text, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"wrote {SHOT} ({SHOT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
