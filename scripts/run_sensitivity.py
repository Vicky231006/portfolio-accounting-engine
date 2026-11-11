"""Run the frozen M8 sensitivity study and write reproducible E9 evidence.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql://postgres:<password>@127.0.0.1:5434/bitemporal_ledger"
    python scripts/run_sensitivity.py --out-dir results

The config must have ``status: frozen``. Existing result files are not
overwritten unless ``--force`` is supplied, so the original evidence can be
archived first.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bitemporal_ledger.evaluation.sensitivity import run_study

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ("sensitivity_detail.csv", "sensitivity_summary.json", "E9_COVERAGE.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen M8/E9 sensitivity study")
    parser.add_argument("--config", default=str(ROOT / "config" / "sensitivity.yaml"))
    parser.add_argument("--out-dir", default=str(ROOT / "results"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--force", action="store_true", help="Overwrite existing result files")
    args = parser.parse_args(argv)

    if not args.database_url:
        raise RuntimeError("DATABASE_URL is not set (or pass --database-url)")
    out_dir = Path(args.out_dir)
    existing = [name for name in OUTPUTS if (out_dir / name).exists()]
    if existing and not args.force:
        print(
            "Refusing to overwrite existing evidence: " + ", ".join(existing) + "\n"
            "Archive the previous run first (for example under results/archive/) "
            "or pass --force.",
            file=sys.stderr,
        )
        return 2

    summary = run_study(args.database_url, args.config, out_dir)
    coverage = summary["e9_coverage"]
    print(f"detail_rows={summary['detail_rows']}")
    print(f"eligible_schemes={coverage['eligible_schemes']} selected_paths={coverage['selected_paths']}")
    print(f"windows_with_instalments={coverage['windows_with_instalments']} solved={coverage['solved']} excluded={coverage['excluded']}")
    print(f"status_counts={coverage['status_counts']}")
    print(f"config_sha256={summary['config_sha256']}")
    print(f"outputs written to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
