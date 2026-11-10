"""Unit tests for the FundLens raw-file NAV adapter (M1)."""

from __future__ import annotations

import gzip
from datetime import date
from decimal import Decimal
from pathlib import Path

from bitemporal_ledger.navigation.fundlens_adapter import FundLensRawNavAdapter

_OPEN_ENDED_MID_CAP = "Open Ended Schemes ( Equity Scheme - Mid Cap Fund )"
_AMC_LINE = "Some Mutual Fund"
_VALID_LINE = "119436;Some Mutual Fund - Growth - Direct Plan;Direct Plan;GROWTH;INF123;;840.79;01-Jan-2024"


def _write_gzip(path: Path, lines: list[str]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        for ln in lines:
            fh.write(ln + "\r\n")


def test_file_sha256_and_scan(tmp_path: Path) -> None:
    p = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    _write_gzip(p, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    adapter = FundLensRawNavAdapter(tmp_path)
    digest = adapter.file_sha256(p)
    scan = adapter.scan([p])
    assert len(scan.observations) == 1
    obs = scan.observations[0]
    assert obs.amfi_scheme_code == "119436"
    assert obs.nav_date == date(2024, 1, 1)
    assert obs.nav == Decimal("840.79")
    assert obs.option_type == "GROWTH"
    assert obs.source_file_sha256 == digest
    assert scan.rejected_duplicates == []


def test_duplicate_same_nav_is_idempotent(tmp_path: Path) -> None:
    p1 = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    p2 = tmp_path / "amfi_nav_20260101_20260331_bbbbbbbbbbbb.txt.gz"
    _write_gzip(p1, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    _write_gzip(p2, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan(adapter.discover())
    assert len(scan.observations) == 1
    assert scan.rejected_duplicates == []


def test_duplicate_different_nav_is_rejected(tmp_path: Path) -> None:
    p1 = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    p2 = tmp_path / "amfi_nav_20260101_20260331_bbbbbbbbbbbb.txt.gz"
    _write_gzip(p1, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    _write_gzip(p2, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE.replace("840.79", "99.99")])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan(adapter.discover())
    assert len(scan.observations) == 1
    assert len(scan.rejected_duplicates) == 1
    scheme, nav_date, original_nav, conflicting_nav, source_file_sha256 = scan.rejected_duplicates[0]
    assert scheme == "119436"
    assert nav_date == date(2024, 1, 1)
    assert original_nav == Decimal("840.79")
    assert conflicting_nav == Decimal("99.99")
    assert len(source_file_sha256) == 64


def test_select_canonical_is_deterministic(tmp_path: Path) -> None:
    p1 = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    p2 = tmp_path / "amfi_nav_20260101_20260331_bbbbbbbbbbbb.txt.gz"
    _write_gzip(p1, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    _write_gzip(p2, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE])
    adapter = FundLensRawNavAdapter(tmp_path)
    files = adapter.discover()
    chosen = adapter.select_canonical(files)
    assert len(chosen) == 1
    assert chosen[0] == min(files, key=lambda p: (adapter.file_sha256(p), p.name))


def test_out_of_scope_idcw_option_is_excluded(tmp_path: Path) -> None:
    p = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    _write_gzip(p, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE.replace("GROWTH", "IDCW")])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan([p])
    assert scan.observations == []
    assert scan.rejected_duplicates == []


def test_malformed_row_field_count_is_excluded(tmp_path: Path) -> None:
    p = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    _write_gzip(p, [_OPEN_ENDED_MID_CAP, _AMC_LINE, "119436;Some Fund;Direct Plan;GROWTH;INF123;;840.79"])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan([p])
    assert scan.observations == []
    assert scan.rejected_duplicates == []


def test_nav_outside_calendar_range_is_excluded(tmp_path: Path) -> None:
    p = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    _write_gzip(p, [_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE.replace("01-Jan-2024", "31-Dec-2041")])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan([p])
    assert scan.observations == []
    assert scan.rejected_duplicates == []


def test_category_outside_scope_is_excluded(tmp_path: Path) -> None:
    p = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    _write_gzip(p, ["Open Ended Schemes ( Equity Scheme - Sectoral / Thematic Fund )", _AMC_LINE, _VALID_LINE])
    adapter = FundLensRawNavAdapter(tmp_path)
    scan = adapter.scan([p])
    assert scan.observations == []
    assert scan.rejected_duplicates == []
