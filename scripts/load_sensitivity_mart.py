"""Load M8 sensitivity results into marts.sensitivity_* tables for Power BI.

Reads committed results/sensitivity_summary.json and results/sensitivity_detail.csv.
Idempotent (truncate + reload). Uses DATABASE_URL.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
DSN = os.environ["DATABASE_URL"]


def main() -> None:
    summary = json.loads((ROOT / "results/sensitivity_summary.json").read_text(encoding="utf-8"))
    detail_path = ROOT / "results/sensitivity_detail.csv"

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS marts")
            cur.execute("DROP TABLE IF EXISTS marts.sensitivity_e9 CASCADE")
            cur.execute("DROP TABLE IF EXISTS marts.sensitivity_scenario CASCADE")
            cur.execute("DROP TABLE IF EXISTS marts.sensitivity_detail_agg CASCADE")
            cur.execute(
                """
                CREATE TABLE marts.sensitivity_e9 (
                    observation_key text,
                    scheme text,
                    window_start date,
                    drawdown_bp numeric,
                    xirr_minus_twr_bp numeric,
                    solved boolean
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE marts.sensitivity_scenario (
                    scenario_key text PRIMARY KEY,
                    scenario text,
                    metric text,
                    parameter text,
                    n integer,
                    median_signed_bp numeric,
                    median_absolute_bp numeric,
                    p95_absolute_bp numeric
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE marts.sensitivity_detail_agg (
                    scenario text,
                    parameter_value text,
                    n integer,
                    median_abs_xirr_bp numeric,
                    median_abs_twr_bp numeric,
                    p95_abs_xirr_bp numeric
                )
                """
            )

            e9_rows = []
            for row in summary.get("e9", []):
                gap = row.get("xirr_minus_twr_bp") or None
                dd = row.get("drawdown_bp") or None
                scheme = row.get("scheme")
                ws = row.get("window_start")
                solved = gap is not None
                obs_key = f"{scheme}|{ws}" if solved and scheme is not None and ws is not None else None
                e9_rows.append((obs_key, scheme, ws, dd, gap, solved))
            cur.executemany(
                "INSERT INTO marts.sensitivity_e9 (observation_key,scheme,window_start,drawdown_bp,xirr_minus_twr_bp,solved) VALUES (%s,%s,%s,%s,%s,%s)",
                e9_rows,
            )

            scen_rows = []
            for key, val in (summary.get("scenarios") or {}).items():
                parts = key.split("|")
                scenario = parts[0] if len(parts) > 0 else key
                metric = parts[1] if len(parts) > 1 else ""
                parameter = parts[2] if len(parts) > 2 else ""
                def num(x):
                    return x if x not in ("", None) else None
                scen_rows.append(
                    (
                        key,
                        scenario,
                        metric,
                        parameter,
                        int(val.get("n") or 0),
                        num(val.get("median_signed_bp")),
                        num(val.get("median_absolute_bp")),
                        num(val.get("p95_absolute_bp")),
                    )
                )
            cur.executemany(
                "INSERT INTO marts.sensitivity_scenario (scenario_key,scenario,metric,parameter,n,median_signed_bp,median_absolute_bp,p95_absolute_bp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                scen_rows,
            )

            # aggregate detail by scenario/parameter for chart-friendly mart
            from collections import defaultdict
            agg = defaultdict(lambda: {"xirr_abs": [], "twr_abs": []})
            with detail_path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    key = (row.get("scenario") or "", row.get("parameter_value") or "")
                    for col, dest in [("xirr_abs_bp", "xirr_abs"), ("twr_abs_bp", "twr_abs")]:
                        v = row.get(col) or ""
                        if v:
                            try:
                                from decimal import Decimal
                                agg[key][dest].append(Decimal(v))
                            except Exception:
                                pass
            def q(vals, p):
                if not vals:
                    return None
                s = sorted(vals)
                n = len(s)
                from decimal import Decimal
                k = (Decimal(str(p)) * (n - 1))
                i = int(k)
                j = min(i + 1, n - 1)
                frac = k - Decimal(i)
                return s[i] * (Decimal(1) - frac) + s[j] * frac
            agg_rows = []
            for (scen, param), vals in agg.items():
                xs = vals["xirr_abs"]
                ts = vals["twr_abs"]
                n = max(len(xs), len(ts))
                agg_rows.append((scen, param, n, q(xs, 0.5), q(ts, 0.5), q(xs, 0.95)))
            cur.executemany(
                "INSERT INTO marts.sensitivity_detail_agg (scenario,parameter_value,n,median_abs_xirr_bp,median_abs_twr_bp,p95_abs_xirr_bp) VALUES (%s,%s,%s,%s,%s,%s)",
                agg_rows,
            )
        conn.commit()
    print(f"loaded e9={len(e9_rows)} scenarios={len(scen_rows)} detail_agg={len(agg_rows)}")


if __name__ == "__main__":
    main()
