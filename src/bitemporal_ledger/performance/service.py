"""Account performance service (M5): builds TWR / Dietz / XIRR from M4 valuations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from bitemporal_ledger.performance import dietz, twr, xirr
from bitemporal_ledger.performance.models import FlowPoint, PerformanceResult
from bitemporal_ledger.valuation.service import ValuationService


class PerformanceService:
    def __init__(self, valuation: ValuationService) -> None:
        self.valuation = valuation

    def compute(
        self,
        account_id: int,
        start_date: date,
        end_date: date,
        known_as_of: datetime,
    ) -> PerformanceResult:
        """Compute period returns for (account, [start_date, end_date], K)."""
        visible = self.valuation.ledger.get_as_of(known_as_of)
        txns = [txn for txn in visible if txn.account_id == account_id]
        flows_by_date: dict[date, Decimal] = {}
        for txn in txns:
            if txn.txn_type == "CONTRIBUTION" and start_date <= txn.effective_date <= end_date:
                flows_by_date[txn.effective_date] = flows_by_date.get(txn.effective_date, Decimal("0")) + (txn.amount_instructed or Decimal("0"))
            elif txn.txn_type == "WITHDRAWAL" and start_date <= txn.effective_date <= end_date:
                flows_by_date[txn.effective_date] = flows_by_date.get(txn.effective_date, Decimal("0")) - (txn.amount_instructed or Decimal("0"))
            elif txn.txn_type == "SIP_INSTALMENT" and start_date <= txn.effective_date <= end_date:
                # SIP contribution leg is the external flow (counted once).
                flows_by_date[txn.effective_date] = flows_by_date.get(txn.effective_date, Decimal("0")) + (txn.amount_instructed or Decimal("0"))
        flow_dates = sorted(flows_by_date)

        def eod(day: date) -> Decimal:
            return self.valuation.value(account_id, day, known_as_of).portfolio_value

        start_value = eod(start_date.fromordinal(start_date.toordinal() - 1)) if not (flow_dates and flow_dates[0] == start_date) else self.valuation.value(account_id, start_date.fromordinal(start_date.toordinal() - 1), known_as_of).portfolio_value
        end_value = eod(end_date)
        flow_entries: list[tuple[date, Decimal, Decimal, Decimal]] = []
        for flow_date in flow_dates:
            pre = eod(flow_date.fromordinal(flow_date.toordinal() - 1))
            flow_eod = eod(flow_date)
            flow_entries.append((flow_date, pre, flows_by_date[flow_date], flow_eod))
        twr_value = twr.compute_twr(
            start_value=start_value,
            end_value=end_value,
            flows=flow_entries,
            period_start=start_date,
            period_end=end_date,
        )
        points = [FlowPoint(day, flows_by_date[day]) for day in flow_dates]
        dietz_value = dietz.modified_dietz(
            start_value, points, end_value, period_start=start_date, period_end=end_date,
        )
        # XIRR: investor perspective (contributions/sips negative, withdrawals +
        # terminal positive on the day after end_date per the inclusive
        # full-calendar-day convention).
        xirr_flows: list[tuple[date, Decimal]] = []
        for txn in txns:
            if not start_date <= txn.effective_date <= end_date:
                continue
            if txn.txn_type in ("CONTRIBUTION", "SIP_INSTALMENT"):
                xirr_flows.append((txn.effective_date, -(txn.amount_instructed or Decimal("0"))))
            elif txn.txn_type == "WITHDRAWAL":
                xirr_flows.append((txn.effective_date, txn.amount_instructed or Decimal("0")))
        terminal_date = end_date + __import__("datetime").timedelta(days=1)
        xirr_flows.append((terminal_date, end_value))
        xirr_result = xirr.solve(xirr_flows)
        return PerformanceResult(
            twr=twr_value,
            modified_dietz=dietz_value,
            xirr=xirr_result,
            start_value=start_value,
            end_value=end_value,
            flows=tuple(points),
            period_start=start_date,
            period_end=end_date,
        )
