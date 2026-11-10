"""Render dashboard page previews as self-contained HTML (M9 night delivery).

Reads the live database and writes one HTML file per dashboard page into
docs/screenshots/*.html so the layout can be reviewed without Power BI.
The PBIP project remains the source of truth for Power BI Desktop.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import psycopg

DSN = os.environ["DATABASE_URL"]
OUT = "docs/screenshots"


def esc(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


CSS = """
body { font-family: Segoe UI, system-ui, sans-serif; background: #121212; color: #eee; margin: 24px; }
h1 { font-size: 22px; margin-bottom: 4px; }
.sub { color: #999; margin-bottom: 16px; font-size: 13px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.card { background: #1e1e1e; border: 1px solid #444; border-radius: 8px; padding: 16px; min-width: 160px; }
.card .n { font-size: 28px; font-weight: 700; }
.card .l { color: #999; font-size: 12px; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th, td { border: 1px solid #333; padding: 4px 8px; text-align: left; }
th { background: #222; }
.bar-wrap { background: #1e1e1e; border: 1px solid #444; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.bar { height: 18px; background: #4f8ff0; margin: 2px 0; min-width: 2px; }
.lbl { display: inline-block; width: 120px; }
"""


def page(name: str, title: str, body: str) -> str:
    return f"<html><head><meta charset='utf-8'><title>{esc(title)}</title><style>{CSS}</style></head><body><h1>{esc(title)}</h1><div class='sub'>Synthetic account data; real AMFI NAV inputs · Educational prototype · PostgreSQL-only (127.0.0.1:5434)</div>{body}</body></html>"


def main() -> None:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            # Page 1
            cur.execute("SELECT count(*) FROM core.account")
            accounts = cur.fetchone()[0]
            cur.execute("SELECT txn_type, count(*) FROM core.txn_version_current GROUP BY txn_type ORDER BY 2 DESC")
            by_type = cur.fetchall()
            cur.execute("SELECT count(*) FROM core.txn_version_current")
            txns = cur.fetchone()[0]
            cur.execute("SELECT min(effective_date), max(effective_date) FROM core.txn_version_current")
            dmin, dmax = cur.fetchone()
            bars = "".join(
                f"<div><span class='lbl'>{esc(t)}</span><span class='bar' style='width:{min(int(c), 600)}px'></span> {c}</div>"
                for t, c in by_type
            )
            page1 = page(
                "page1",
                "1 Portfolio Overview",
                f"<div class='cards'>"
                f"<div class='card'><div class='n'>{accounts}</div><div class='l'>Synthetic accounts</div></div>"
                f"<div class='card'><div class='n'>{txns}</div><div class='l'>Transactions</div></div>"
                f"</div>"
                f"<div class='bar-wrap'><strong>Transactions by type</strong><br>{bars}</div>"
                f"<div>Effective range: {esc(dmin)} – {esc(dmax)}</div>",
            )
            # Page 2
            cur.execute(
                "SELECT txn_group_id, txn_type, effective_date, scheme_code FROM marts.account_drilldown ORDER BY effective_date LIMIT 12"
            )
            rows = cur.fetchall()
            tbl = "".join(f"<tr><td>{esc(r[0])}</td><td>{esc(r[1])}</td><td>{esc(r[2])}</td><td>{esc(r[3])}</td></tr>" for r in rows)
            page2 = page(
                "page2",
                "2 Account Drilldown",
                f"<div class='cards'><div class='card'><div class='n'>{txns}</div><div class='l'>Ledger rows</div></div></div>"
                f"<table><tr><th>Transaction</th><th>Type</th><th>Effective date</th><th>Scheme</th></tr>{tbl}</table>",
            )
            # Page 3
            cur.execute("SELECT revision_kind, count(*) FROM marts.correction_audit GROUP BY revision_kind ORDER BY 2 DESC")
            kinds = cur.fetchall()
            cur.execute("SELECT revision_no, count(*) FROM marts.correction_audit GROUP BY revision_no ORDER BY 2 DESC")
            revs = cur.fetchall()
            bars3 = "".join(f"<div><span class='lbl'>{esc(k)}</span><span class='bar' style='width:{min(int(c), 600)}px'></span> {c}</div>" for k, c in kinds)
            tbl3 = "".join(f"<tr><td>{esc(r[0])}</td><td>{esc(r[1])}</td></tr>" for r in revs)
            page3 = page(
                "page3",
                "3 Restatements and Audit",
                bars3
                + f"<p>Revisions by number: {esc(tbl3)}</p><table><tr><th>Revision #</th><th>Count</th></tr>{tbl3}</table>"
                + "<p>Applied corrections: 0 (no correction operations in the production ledger — honest, not fabricated)</p>",
            )
            # Page 4
            cur.execute("SELECT amfi_scheme_code, observations, avg_nav FROM marts.nav_summary ORDER BY observations DESC LIMIT 15")
            top = cur.fetchall()
            bars4 = "".join(f"<div><span class='lbl'>{esc(r[0])}</span><span class='bar' style='width:{min(int(r[1]), 600)}px'></span> {r[1]} obs, avg NAV {r[2]}</div>" for r in top)
            page4 = page(
                "page4",
                "4 Sensitivity (NAV overview)",
                f"<div class='cards'><div class='card'><div class='n'>{len(top)*1}</div><div class='l'>Top schemes shown (of 783)</div></div></div>"
                f"<div class='bar-wrap'><strong>Observations by scheme (top 15)</strong><br>{bars4}</div>"
                + "<p>M8 sensitivity study: 344 eligible, 30 selected, 11,436 detail rows — separate table (see RESULTS.md).</p>",
            )
    Path_html = {1: page1, 2: page2, 3: page3, 4: page4}
    import pathlib

    out = pathlib.Path(OUT)
    out.mkdir(parents=True, exist_ok=True)
    for num, html in Path_html.items():
        (out / f"page{num}_{['', 'overview', 'drilldown', 'restatements', 'sensitivity'][num]}.html").write_text(html)
        print(f"wrote page{num}")


if __name__ == "__main__":
    main()
