"""FundLens verified raw-file NAV adapter (M1, FundLens Option A fallback).

Read-only consumption of AMFI NAV gzip files from a source directory, following
the FundLens verified parser and scope contract recorded in ``docs/FUNDLES_NAV_CONTRACT.md``:

- File format: semicolon-delimited, CRLF; eight fields per data line:
  ``Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div
  Reinvestment;Net Asset Value;Date``.
- Section headers: ``Open Ended Schemes ( Equity Scheme - Mid Cap Fund )`` and
  similar; only open-ended sections whose sub-category maps into the approved
  category scope are loaded. Legacy headers such as ``( Growth )`` hold schemes
  that are not re-categorised and are excluded.
- Plans: ``DIRECT`` and ``REGULAR`` (ingested; analytics default to ``DIRECT``).
- Options: ``GROWTH`` only (``IDCW`` rows are out of scope).
- History: ``2006-04-01 .. 2040-12-31``; calendar bounds ``2006-01-01 .. 2040-12-31``.
- Dates: ``DD-Mon-YYYY`` (for example ``01-Jan-2024``).
- NAVs: parsed as ``Decimal``, never ``float``; non-finite or unparseable values
  are rejected.

Duplicate ``(scheme_code, nav_date)`` handling: identical NAV is an idempotent
skip; a differing NAV is rejected as a conflict (never silently overwritten).

Checksum and provenance are captured per source file; database import is applied
via ``scripts/import_nav.py`` once the PostgreSQL 16 service is available.
"""

from __future__ import annotations

import gzip
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

_FILENAME_RE = re.compile(r"^amfi_nav_(\d{8})_(\d{8})_([0-9a-f]{12})\.txt\.gz$")
_SECTION_RE = re.compile(r"^(Open Ended|Close Ended|Interval Fund) Schemes?\s*\((.*)\)\s*$", re.I)
_EQUITY_SUB_RE = re.compile(r"^Equity Schemes?\s*-\s*(.+)$", re.I)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_RE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_IDCW_WORDS = ("idcw", "dividend", "payout", "reinvest")
_COLUMN_HEADER_PREFIX = "Scheme Code;"
_EXPECTED_FIELDS = 8
CALENDAR_MIN = date(2006, 1, 1)
CALENDAR_MAX = date(2040, 12, 31)
SCOPE_START = date(2006, 4, 1)
SCOPE_END = date(2040, 12, 31)
PLANS = frozenset({"DIRECT", "REGULAR"})
OPTIONS = frozenset({"GROWTH"})
SCOPE_CATEGORIES: dict[str, str] = {
    "large cap fund": "Large Cap",
    "large & mid cap fund": "Large & Mid Cap",
    "mid cap fund": "Mid Cap",
    "small cap fund": "Small Cap",
    "multi cap fund": "Multi Cap",
    "flexi cap fund": "Flexi Cap",
    "focused fund": "Focused",
    "value fund": "Value",
    "contra fund": "Contra",
    "dividend yield fund": "Dividend Yield",
    "elss": "ELSS",
    "elss- tax saver fund": "ELSS",
}


@dataclass(frozen=True)
class NavObservation:
    amfi_scheme_code: str
    nav_date: date
    nav: Decimal
    option_type: str
    source_file_sha256: str


@dataclass(frozen=True)
class AdapterScan:
    observations: list[NavObservation]
    rejected_duplicates: list[tuple[str, date, Decimal, Decimal, str]]


@dataclass(frozen=True)
class _Section:
    kind: str  # "open ended" | "close ended" | "interval fund"
    header: str
    category: str | None


@dataclass(frozen=True)
class _StagedRow:
    line_no: int
    section_header: str
    amc_name: str | None
    raw_text: str
    scheme_code: str | None
    scheme_name: str | None
    plan_raw: str | None
    option_raw: str | None
    isin_payout: str | None
    isin_reinvest: str | None
    nav_raw: str | None
    date_raw: str | None
    nav: Decimal | None
    nav_date: date | None
    category: str | None
    plan_type: str | None
    option_type: str | None
    parse_status: str  # VALID | REJECTED | DUPLICATE
    reject_reason: str | None


class FundLensRawNavAdapter:
    def __init__(self, source_dir: str | Path) -> None:
        self.source_dir = Path(source_dir)

    # ------------------------------------------------------------------ files

    def discover(self) -> list[Path]:
        return sorted(p for p in self.source_dir.rglob("amfi_nav_*.txt.gz") if _FILENAME_RE.match(p.name))

    def file_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with gzip.open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------ parsing

    @staticmethod
    def _clean(value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @staticmethod
    def _parse_amfi_date(text: str | None) -> date | None:
        if not text:
            return None
        m = _DATE_RE.match(text.strip())
        if not m:
            return None
        month = _MONTHS.get(m.group(2).lower())
        if month is None:
            return None
        try:
            return date(int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            return None

    @staticmethod
    def _parse_nav(text: str | None) -> Decimal | None:
        if not text or not text.strip():
            return None
        try:
            value = Decimal(text.strip())
        except InvalidOperation:
            return None
        return value if value.is_finite() else None

    @staticmethod
    def _derive_plan(plan_raw: str | None, name: str | None) -> str:
        text = (plan_raw or "").lower()
        if "direct" in text:
            return "DIRECT"
        if "regular" in text:
            return "REGULAR"
        return "DIRECT" if "direct" in (name or "").lower() else "REGULAR"

    @staticmethod
    def _derive_option(option_raw: str | None, name: str | None) -> str:
        for text in ((option_raw or "").lower(), (name or "").lower()):
            if not text:
                continue
            if any(w in text for w in _IDCW_WORDS):
                return "IDCW"
            if "growth" in text:
                return "GROWTH"
        return "UNKNOWN"

    @staticmethod
    def _parse_section_header(line: str) -> _Section | None:
        m = _SECTION_RE.match(line.strip())
        if not m:
            return None
        kind = m.group(1).lower()
        inner = m.group(2).strip()
        category: str | None = None
        if kind == "open ended":
            sub = _EQUITY_SUB_RE.match(inner)
            if sub is not None:
                key = re.sub(r"\s+", " ", sub.group(1)).strip().lower()
                category = SCOPE_CATEGORIES.get(key)
        return _Section(kind=kind, header=line.strip(), category=category)

    def _stage_line(self, line_no: int, raw_text: str, section: _Section | None, amc: str | None) -> _StagedRow | None:
        """Return a staged row for in-scope data lines; None when out of scope."""
        fields = raw_text.split(";")
        if len(fields) != _EXPECTED_FIELDS:
            return None
        code, name, plan_raw, option_raw, _isin_p, _isin_r, nav_raw, date_raw = (f.strip() for f in fields)
        plan_type = self._derive_plan(plan_raw, name)
        option_type = self._derive_option(option_raw, name)
        if plan_type not in PLANS or option_type not in OPTIONS:
            return None
        reasons: list[str] = []
        if not code or not code.isdigit():
            reasons.append("missing or non-numeric scheme code")
        if not name:
            reasons.append("missing scheme name")
        nav = self._parse_nav(nav_raw)
        if nav is None:
            reasons.append(f"unparseable NAV {nav_raw!r}")
        nav_date = self._parse_amfi_date(date_raw)
        if nav_date is None:
            reasons.append(f"unparseable date {date_raw!r}")
        elif not (CALENDAR_MIN <= nav_date <= CALENDAR_MAX):
            reasons.append(f"date {nav_date} outside supported calendar range")
        if reasons:
            return None
        return _StagedRow(
            line_no=line_no,
            section_header=section.header if section else "",
            amc_name=amc,
            raw_text=raw_text,
            scheme_code=code,
            scheme_name=name,
            plan_raw=self._clean(plan_raw),
            option_raw=self._clean(option_raw),
            isin_payout=self._clean(_isin_p),
            isin_reinvest=self._clean(_isin_r),
            nav_raw=self._clean(nav_raw),
            date_raw=self._clean(date_raw),
            nav=nav,
            nav_date=nav_date,
            category=section.category if section else None,
            plan_type=plan_type,
            option_type=option_type,
            parse_status="VALID",
            reject_reason=None,
        )

    def scan(self, files: list[Path]) -> AdapterScan:
        """Scan canonical source files, returning accepted observations and conflicts."""
        observations: list[NavObservation] = []
        rejections: list[tuple[str, date, Decimal, Decimal]] = []
        seen: dict[tuple[str, date], Decimal] = {}
        for path in sorted(files):
            digest = self.file_sha256(path)
            section: _Section | None = None
            amc: str | None = None
            file_seen: set[tuple[str, date]] = set()
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                for line_no, line in enumerate(fh, start=1):
                    text = line.rstrip("\r\n").strip()
                    if not text or text.startswith(_COLUMN_HEADER_PREFIX):
                        continue
                    header = self._parse_section_header(text)
                    if header is not None:
                        section, amc = header, None
                        continue
                    if ";" not in text:
                        amc = text.strip()
                        continue
                    if section is None or section.category is None:
                        continue
                    row = self._stage_line(line_no, text, section, amc)
                    if row is None or row.parse_status != "VALID":
                        continue
                    key = (row.scheme_code, row.nav_date)
                    if key in file_seen:
                        continue  # repeated (scheme_code, date) within one file: never loaded
                    file_seen.add(key)
                    prev = seen.get(key)
                    if prev is None:
                        seen[key] = row.nav
                        observations.append(
                            NavObservation(
                                amfi_scheme_code=row.scheme_code,
                                nav_date=row.nav_date,
                                nav=row.nav,
                                option_type=row.option_type,
                                source_file_sha256=digest,
                            )
                        )
                    elif prev == row.nav:
                        continue  # idempotent re-observation
                    else:
                        rejections.append((key[0], key[1], prev, row.nav, digest))
        return AdapterScan(observations=observations, rejected_duplicates=rejections)

    def select_canonical(self, files: list[Path]) -> list[Path]:
        """Deterministic canonical selection for duplicate source ranges.

        Files are grouped by (start_date, end_date) from the filename; one file
        per group is selected deterministically (smallest source SHA-256, then
        filename). Both duplicate files are preserved by the caller; the
        canonical selection is used for ingestion.
        """
        groups: dict[tuple[str, str], list[Path]] = {}
        for p in files:
            m = _FILENAME_RE.match(p.name)
            if not m:
                continue
            groups.setdefault((m.group(1), m.group(2)), []).append(p)
        chosen: list[Path] = []
        for key in sorted(groups):
            group = groups[key]
            chosen.append(min(group, key=lambda p: (self.file_sha256(p), p.name)))
        return sorted(chosen)
