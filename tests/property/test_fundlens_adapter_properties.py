"""Property-style invariants for the FundLens raw-file NAV adapter (M1)."""

from __future__ import annotations

import gzip
from pathlib import Path

from bitemporal_ledger.navigation.fundlens_adapter import FundLensRawNavAdapter

_OPEN_ENDED_MID_CAP = "Open Ended Schemes ( Equity Scheme - Mid Cap Fund )"
_AMC_LINE = "Some Mutual Fund"
_VALID_LINE = "119436;Some Mutual Fund - Growth - Direct Plan;Direct Plan;GROWTH;INF123;;840.79;01-Jan-2024"


def test_adapter_invariants(tmp_path: Path) -> None:
    p1 = tmp_path / "amfi_nav_20260101_20260331_aaaaaaaaaaaa.txt.gz"
    p2 = tmp_path / "amfi_nav_20260101_20260331_bbbbbbbbbbbb.txt.gz"
    for p in (p1, p2):
        with gzip.open(p, "wt", encoding="utf-8", newline="") as fh:
            for ln in (_OPEN_ENDED_MID_CAP, _AMC_LINE, _VALID_LINE):
                fh.write(ln + "\r\n")

    adapter = FundLensRawNavAdapter(tmp_path)
    files = adapter.discover()
    chosen = adapter.select_canonical(files)
    assert len(chosen) == 1
    assert len(adapter.discover()) == 2

    scan = adapter.scan(files)
    assert len(scan.observations) == 1
    assert scan.observations[0].source_file_sha256 == adapter.file_sha256(chosen[0])
    assert len({o.source_file_sha256 for o in scan.observations}) == 1
