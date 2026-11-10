"""NAV price/date index for the M2 generator (M2, D-036).

The generator needs only two read-only capabilities from the M1 NAV snapshot:
prices on a given date, and the first NAV date on or after a date. Both are
served from an in-memory index built from the snapshot; the generator never
writes to the snapshot. Unit tests build the index in memory; the CLI builds
it from PostgreSQL with read-only SELECTs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class NavSeries:
    scheme_code: str
    dates: tuple[date, ...]
    prices: dict[date, Decimal]


class NavIndex:
    """Read-only mapping of scheme code to its NAV series."""

    def __init__(self, series: dict[str, NavSeries]) -> None:
        self._series = dict(series)

    @classmethod
    def from_mapping(cls, mapping: dict[str, list[tuple[date, Decimal]]]) -> NavIndex:
        series: dict[str, NavSeries] = {}
        for code in sorted(mapping):
            rows = sorted(mapping[code], key=lambda row: row[0])
            series[code] = NavSeries(
                scheme_code=code,
                dates=tuple(d for d, _price in rows),
                prices={d: p for d, p in rows},
            )
        return cls(series)

    @property
    def scheme_codes(self) -> list[str]:
        return sorted(self._series)

    def series(self, scheme_code: str) -> NavSeries:
        return self._series[scheme_code]

    def has_scheme(self, scheme_code: str) -> bool:
        return scheme_code in self._series

    def price(self, scheme_code: str, nav_date: date) -> Decimal | None:
        series = self._series.get(scheme_code)
        if series is None:
            return None
        return series.prices.get(nav_date)

    def first_nav_on_or_after(
        self, scheme_code: str, nav_date: date, max_calendar_days: int = 5
    ) -> date | None:
        """First NAV date on or after ``nav_date`` within ``max_calendar_days``."""
        series = self._series.get(scheme_code)
        if series is None:
            return None
        for candidate in series.dates:
            if candidate < nav_date:
                continue
            if (candidate - nav_date).days <= max_calendar_days:
                return candidate
            return None
        return None

    def dates_between(self, scheme_code: str, start: date, end: date) -> list[date]:
        series = self._series.get(scheme_code)
        if series is None:
            return []
        return [d for d in series.dates if start <= d <= end]


def load_nav_index_from_db(dsn: str, snapshot_id: int, scheme_codes: list[str]) -> NavIndex:
    """Build a :class:`NavIndex` from the M1 snapshot with read-only SELECTs."""
    import psycopg

    mapping: dict[str, list[tuple[date, Decimal]]] = {code: [] for code in scheme_codes}
    if not scheme_codes:
        return NavIndex.from_mapping(mapping)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT amfi_scheme_code, nav_date, nav FROM core.nav_observation"
                " WHERE nav_snapshot_id = %s ORDER BY amfi_scheme_code, nav_date",
                (snapshot_id,),
            )
            for scheme_code, nav_date, nav in cur.fetchall():
                if scheme_code in mapping:
                    mapping[scheme_code].append((nav_date, nav))
    return NavIndex.from_mapping(mapping)


def eligible_scheme_codes_from_db(
    dsn: str,
    snapshot_id: int,
    min_observations: int,
    min_first_nav_date: date,
    max_paths: int,
) -> list[str]:
    """Deterministic eligible-scheme pool (mirrors the sensitivity rule)."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT amfi_scheme_code FROM core.nav_observation"
                " WHERE nav_snapshot_id = %s"
                " GROUP BY amfi_scheme_code"
                " HAVING count(*) >= %s AND min(nav_date) <= %s"
                " ORDER BY amfi_scheme_code",
                (snapshot_id, min_observations, min_first_nav_date),
            )
            codes = [row[0] for row in cur.fetchall()]
    return codes[:max_paths]
