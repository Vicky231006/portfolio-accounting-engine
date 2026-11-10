"""Build historical portfolio valuation marts from M4 ValuationService.

Deterministic: fixed month-end dates and fixed knowledge time (RUN_K).
No financial methodology changes; uses approved valuation service only.
"""

from __future__ import annotations

import calendar
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg

sys.path.insert(0, "/app/src")
from bitemporal_ledger.ledger.service import LedgerService
from bitemporal_ledger.valuation.service import ValuationService, ValuationError, InvariantError

DSN = os.environ["DATABASE_URL"]
RUN_K = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)


def month_ends(start: date, end: date):
    y, m = start.year, start.month
    while True:
        last = date(y, m, calendar.monthrange(y, m)[1])
        if last > end:
            break
        if last >= start:
            yield last
        m += 1
        if m > 12:
            m = 1
            y += 1


def main() -> None:
    ledger = LedgerService(DSN, 3)
    val = ValuationService(DSN, 3, ledger)
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT account_id FROM core.account ORDER BY account_id")
            accounts = [r[0] for r in cur.fetchall()]
            cur.execute("CREATE SCHEMA IF NOT EXISTS marts")
            cur.execute("DROP TABLE IF EXISTS marts.portfolio_history CASCADE")
            cur.execute("DROP TABLE IF EXISTS marts.holdings_latest CASCADE")
            cur.execute(
                """CREATE TABLE marts.portfolio_history (
                    account_id int,
                    valuation_date date,
                    total_value numeric,
                    cash numeric,
                    holdings_value numeric,
                    stale_value numeric,
                    status text
                )"""
            )
            cur.execute(
                """CREATE TABLE marts.holdings_latest (
                    account_id int,
                    valuation_date date,
                    scheme_code text,
                    scheme_display text,
                    units numeric,
                    nav numeric,
                    nav_date date,
                    market_value numeric,
                    stale_nav boolean,
                    stale_days int
                )"""
            )
        conn.commit()

    # Quarterly month-ends to keep runtime reasonable while giving history.
    dates = [d for d in month_ends(date(2014, 3, 1), date(2026, 9, 30)) if d.month in (3, 6, 9, 12)]
    hist_rows = []
    latest_rows = []
    last_ok = {}
    for d in dates:
        for aid in accounts:
            try:
                vr = val.value(aid, d, RUN_K)
                hist_rows.append((aid, d, vr.portfolio_value, vr.cash, vr.fresh_value + vr.stale_value, vr.stale_value, "OK"))
                last_ok[aid] = (d, vr)
            except (ValuationError, InvariantError) as e:
                hist_rows.append((aid, d, None, None, None, None, getattr(e, "reason_code", "ERROR")))
    # latest holdings per account from most recent successful valuation
    for aid, (d, vr) in last_ok.items():
        for h in vr.holdings:
            latest_rows.append((aid, d, h.scheme_code, f"Scheme {h.scheme_code}", h.units, h.price, h.price_date, h.value, h.is_stale, h.stale_days))

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO marts.portfolio_history (account_id,valuation_date,total_value,cash,holdings_value,stale_value,status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                hist_rows,
            )
            cur.executemany(
                "INSERT INTO marts.holdings_latest (account_id,valuation_date,scheme_code,scheme_display,units,nav,nav_date,market_value,stale_nav,stale_days) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                latest_rows,
            )
            # monthly external flows mart (separate contribution/withdrawal)
            cur.execute("DROP TABLE IF EXISTS marts.monthly_flows CASCADE")
            cur.execute(
                """CREATE TABLE marts.monthly_flows AS
                SELECT
                    date_trunc('month', effective_date)::date AS month,
                    SUM(CASE WHEN external_amount > 0 THEN external_amount ELSE 0 END) AS contributions,
                    SUM(CASE WHEN external_amount < 0 THEN -external_amount ELSE 0 END) AS withdrawals
                FROM marts.cash_flows
                GROUP BY 1
                ORDER BY 1"""
            )
            # portfolio-level (aggregate) history
            cur.execute("DROP TABLE IF EXISTS marts.portfolio_history_total CASCADE")
            cur.execute(
                """CREATE TABLE marts.portfolio_history_total AS
                SELECT valuation_date,
                       SUM(total_value) AS total_value,
                       SUM(cash) AS total_cash,
                       SUM(holdings_value) AS total_holdings_value
                FROM marts.portfolio_history
                WHERE status='OK'
                GROUP BY valuation_date
                ORDER BY valuation_date"""
            )
            # asset allocation (latest holdings, top 10 by market value + Other; display labels)
            cur.execute("DROP TABLE IF EXISTS marts.asset_allocation CASCADE")
            cur.execute(
                """CREATE TABLE marts.asset_allocation AS
                WITH base AS (
                    SELECT scheme_code, SUM(market_value) AS market_value, SUM(units) AS total_units
                    FROM marts.holdings_latest
                    GROUP BY scheme_code
                ), ranked AS (
                    SELECT scheme_code, market_value, total_units,
                           ROW_NUMBER() OVER (ORDER BY market_value DESC) AS rn
                    FROM base
                )
                SELECT
                    CASE WHEN rn <= 10 THEN ('Scheme ' || scheme_code) ELSE 'Other schemes' END AS scheme_display,
                    CASE WHEN rn <= 10 THEN scheme_code ELSE 'OTHER' END AS scheme_code,
                    SUM(market_value) AS market_value,
                    SUM(total_units) AS total_units,
                    MIN(CASE WHEN rn <= 10 THEN rn ELSE 11 END)::int AS sort_order
                FROM ranked
                GROUP BY 1,2"""
            )
        conn.commit()
    print(f"history_rows={len(hist_rows)} latest_holdings={len(latest_rows)} dates={len(dates)} accounts={len(accounts)}")


if __name__ == "__main__":
    main()
