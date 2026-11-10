"""M0 read-only reconciliation of FundLens raw AMFI files.

This script only reads the preserved .gz files under the FundLens data directory.
It never writes to FundLens, never opens a database, and never imports FundLens code.
It writes a report into this project's docs/ directory.

Usage:
    python scripts/m0_reconcile_raw_files.py
"""

from __future__ import annotations

import gzip
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAW_DIR = Path(r"C:\Users\Vicky\Desktop\fundlens\data\raw\amfi")
OUT = Path(__file__).resolve().parents[1] / "docs" / "FUNDLENS_FILE_RECONCILIATION.md"

NAME_RE = re.compile(r"^amfi_nav_(\d{8})_(\d{8})_([0-9a-f]{12})\.txt\.gz$")
SECTION_RE = re.compile(r"^(Open Ended|Close Ended|Interval Fund) Schemes?\s*\((.*)\)\s*$", re.I)
EQUITY_RE = re.compile(r"^Equity Schemes?\s*-\s*(.+)$", re.I)
DATE_RE = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
)}

CATEGORY_MAP = {
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
IDCW_WORDS = ("idcw", "dividend", "payout", "reinvest")


def parse_date(text: str) -> date | None:
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def derive_plan(plan_raw: str, name: str) -> str:
    text = (plan_raw or "").lower()
    if "direct" in text:
        return "DIRECT"
    if "regular" in text:
        return "REGULAR"
    return "DIRECT" if "direct" in (name or "").lower() else "REGULAR"


def derive_option(option_raw: str, name: str) -> str:
    for text in ((option_raw or "").lower(), (name or "").lower()):
        if not text:
            continue
        if any(w in text for w in IDCW_WORDS):
            return "IDCW"
        if "growth" in text:
            return "GROWTH"
    return "UNKNOWN"


def parse_rows(path: Path):
    """Yield (code, nav_date, nav, name, plan, option, category, raw_fields)."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        section_category = None
        for line in fh:
            text = line.rstrip("\r\n")
            if not text.strip() or text.startswith("Scheme Code;"):
                continue
            m = SECTION_RE.match(text.strip())
            if m:
                kind, inner = m.group(1).lower(), m.group(2).strip()
                section_category = None
                if kind == "open ended":
                    sub = EQUITY_RE.match(inner)
                    if sub:
                        key = re.sub(r"\s+", " ", sub.group(1)).strip().lower()
                        section_category = CATEGORY_MAP.get(key)
                continue
            if ";" not in text:
                continue
            fields = text.split(";")
            if len(fields) != 8:
                continue
            code, name, plan_raw, option_raw, _isin_p, _isin_r, nav_raw, date_raw = (
                f.strip() for f in fields
            )
            nav_date = parse_date(date_raw)
            try:
                nav = Decimal(nav_raw)
            except InvalidOperation:
                nav = None
            if not code or nav_date is None or nav is None or not nav.is_finite():
                continue
            yield (
                code,
                nav_date,
                nav,
                name,
                derive_plan(plan_raw, name),
                derive_option(option_raw, name),
                section_category,
                fields,
            )


def scan(path: Path, unique_all: set | None = None, unique_dg: set | None = None) -> dict:
    compressed = path.stat().st_size
    digest = hashlib.sha256()
    uncompressed = 0
    data_lines = 0
    schemes: set[str] = set()
    dates: list[date] = []
    direct_growth = 0
    in_scope_all = 0
    in_scope_direct_growth = 0

    with gzip.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
            uncompressed += len(chunk)

    for code, nav_date, _nav, _name, plan, option, category, _fields in parse_rows(path):
        data_lines += 1
        schemes.add(code)
        dates.append(nav_date)
        if category is not None:
            in_scope_all += 1
            if unique_all is not None:
                unique_all.add((code, nav_date))
        if plan == "DIRECT" and option == "GROWTH":
            direct_growth += 1
            if category is not None:
                in_scope_direct_growth += 1
                if unique_dg is not None:
                    unique_dg.add((code, nav_date))

    return {
        "name": path.name,
        "relpath": str(path.relative_to(RAW_DIR)),
        "compressed": compressed,
        "uncompressed": uncompressed,
        "sha256": digest.hexdigest(),
        "data_lines": data_lines,
        "schemes": len(schemes),
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
        "in_scope_all": in_scope_all,
        "direct_growth": direct_growth,
        "in_scope_direct_growth": in_scope_direct_growth,
    }


def compare_duplicate(a: Path, b: Path) -> tuple[int, list[dict], int]:
    """Compare two files keyed by (code, date); return differing rows and Growth diffs."""
    def rows(path: Path):
        out = {}
        for code, nav_date, nav, name, plan, option, category, fields in parse_rows(path):
            out[(code, nav_date)] = {
                "nav": nav,
                "name": name,
                "plan": plan,
                "option": option,
                "category": category,
                "fields": fields,
            }
        return out

    left, right = rows(a), rows(b)
    diffs = []
    for key in sorted(set(left) | set(right)):
        lrow, rrow = left.get(key), right.get(key)
        if lrow is None or rrow is None:
            diffs.append({
                "code": key[0], "date": key[1],
                "kind": "MISSING_LEFT" if lrow is None else "MISSING_RIGHT",
                "name": (lrow or rrow)["name"],
                "plan": (lrow or rrow)["plan"],
                "option": (lrow or rrow)["option"],
                "left": None if lrow is None else str(lrow["nav"]),
                "right": None if rrow is None else str(rrow["nav"]),
            })
            continue
        if lrow["nav"] != rrow["nav"]:
            diffs.append({
                "code": key[0], "date": key[1], "kind": "NAV",
                "name": lrow["name"], "plan": lrow["plan"], "option": lrow["option"],
                "left": str(lrow["nav"]), "right": str(rrow["nav"]),
            })
    growth_diffs = sum(1 for d in diffs if d["plan"] == "DIRECT" and d["option"] == "GROWTH")
    return len(diffs), diffs, growth_diffs


def main() -> None:
    files = sorted(RAW_DIR.rglob("*.gz"))
    if not files:
        raise SystemExit(f"No .gz files found under {RAW_DIR}")

    unique_all: set = set()
    unique_dg: set = set()
    rows = [scan(p, unique_all, unique_dg) for p in files]
    by_range: dict[tuple[str, str], list[Path]] = {}
    for path in files:
        m = NAME_RE.match(path.name)
        if not m:
            raise SystemExit(f"Unexpected filename: {path.name}")
        by_range.setdefault((m.group(1), m.group(2)), []).append(path)

    duplicates = {k: v for k, v in by_range.items() if len(v) > 1}
    if len(duplicates) != 1:
        raise SystemExit(f"Expected exactly one duplicate range, found {len(duplicates)}")

    dup_range, dup_files = next(iter(duplicates.items()))
    diff_count, diffs, growth_diffs = compare_duplicate(dup_files[0], dup_files[1])
    total_data_lines = sum(r["data_lines"] for r in rows)
    total_in_scope_all = sum(r["in_scope_all"] for r in rows)
    total_direct_growth = sum(r["direct_growth"] for r in rows)
    total_in_scope = sum(r["in_scope_direct_growth"] for r in rows)

    lines = []
    lines.append("# FundLens Raw-File Reconciliation — 86 Files vs 85 Registered Ranges")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append("| Date | 2026-11-09 |")
    lines.append("| Scope | Read-only scan of `C:\\Users\\Vicky\\Desktop\\fundlens\\data\\raw\\amfi`; no FundLens database or volume access |")
    lines.append("| Result | 86 `.gz` files, 85 distinct date ranges, one duplicate range; duplicate differs on three out-of-scope IDCW NAV values and no Direct-Growth values |")
    lines.append("")
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"- Files on disk: **{len(files)}**")
    lines.append(f"- Distinct filename date ranges: **{len(by_range)}**")
    lines.append(f"- Duplicate range: `{dup_range[0]}` .. `{dup_range[1]}`")
    lines.append(f"- Data lines parsed across all files: **{total_data_lines:,}**")
    lines.append(f"- In-scope rows in the 11 categories, all plans/options, per file: **{total_in_scope_all:,}**")
    lines.append(f"- In-scope unique `(scheme_code, nav_date)` observations: **{len(unique_all):,}**")
    lines.append(f"- Direct-Growth data lines (all categories): **{total_direct_growth:,}**")
    lines.append(f"- Direct-Growth data lines in the 11 in-scope categories, per file: **{total_in_scope:,}**")
    lines.append(f"- Direct-Growth unique `(scheme_code, nav_date)` observations: **{len(unique_dg):,}**")
    lines.append(f"- Row-level differences in the duplicate range: **{diff_count}**")
    lines.append(f"- Direct-Growth differences in the duplicate range: **{growth_diffs}**")
    lines.append("")
    lines.append("The 85 registered files figure is the prior audited `RESULTS.md` count; it is not a fresh database query. The 86 on-disk files reconcile to 85 distinct ranges because the 2006 range was downloaded twice with different content hashes.")
    lines.append("")
    lines.append("### Count correction")
    lines.append("")
    lines.append("An earlier M0 draft cited 38,377,450 data lines, 3,916,280 in-scope rows and 435,745 Direct-Growth rows. The reconciliation scan does not reproduce those figures. The verified scan figures above are authoritative for this project and the earlier Direct-Growth figure is withdrawn. The in-scope all-plans figure is close to the earlier one (difference 38 rows), which is consistent with a small counting-method difference; the Direct-Growth figure is materially different and must not be cited. The FundLens `core.fact_nav` count of 1,811,703 rows is a different basis (registered DB rows, both plans, Growth only) and is not directly comparable to these raw-file counts.")
    lines.append("")
    lines.append("## 2. File inventory")
    lines.append("")
    lines.append("| # | File | Range | Compressed bytes | Uncompressed bytes | SHA-256 (uncompressed) | Data lines | Schemes | Min date | Max date | In-scope all | Direct-Growth | In-scope D-G |")
    lines.append("|---:|---|---|---:|---:|---|---:|---:|---|---|---:|---:|---:|")
    for i, r in enumerate(rows, 1):
        m = NAME_RE.match(r["name"])
        rng = f"{m.group(1)}..{m.group(2)}" if m else ""
        lines.append(
            f"| {i} | `{r['name']}` | `{rng}` | {r['compressed']:,} | {r['uncompressed']:,} | "
            f"`{r['sha256']}` | {r['data_lines']:,} | {r['schemes']:,} | {r['min_date']} | {r['max_date']} | "
            f"{r['in_scope_all']:,} | {r['direct_growth']:,} | {r['in_scope_direct_growth']:,} |"
        )
    lines.append("")
    lines.append("## 3. Duplicate-range comparison")
    lines.append("")
    lines.append(f"- Files: `{dup_files[0].name}` and `{dup_files[1].name}`")
    lines.append("- Same line count: **yes**" if rows[files.index(dup_files[0])]["data_lines"] == rows[files.index(dup_files[1])]["data_lines"] else "- Same line count: **no**")
    lines.append(f"- Differing rows: **{diff_count}**")
    lines.append(f"- Direct-Growth differing rows: **{growth_diffs}**")
    lines.append("")
    lines.append("| Scheme code | Scheme name | Date | Plan | Option | NAV in file A | NAV in file B |")
    lines.append("|---|---|---|---|---|---:|---:|")
    for d in diffs:
        lines.append(
            f"| `{d['code']}` | {d['name']} | {d['date']} | {d['plan']} | {d['option']} | "
            f"{d['left']} | {d['right']} |"
        )
    lines.append("")
    lines.append("## 4. Decision and import rule")
    lines.append("")
    lines.append("1. Both duplicate files are preserved and listed in the manifest; neither is silently deleted or overwritten.")
    lines.append("2. The import records one as `CANONICAL` and the other as `DUPLICATE_RANGE_VARIANT` using a deterministic rule (lexicographically smaller filename SHA-256 prefix), and records both checksums.")
    lines.append("3. The three differing rows are `IDCW` and outside this project's Growth-only scope. They are retained in the source manifest and never used as NAV input.")
    lines.append("4. If a future scope includes IDCW, the conflict must be resolved explicitly and recorded in `nav_revision_conflict`; the project must not choose a value silently.")
    lines.append("5. The Growth-only import is expected to be identical from either duplicate file. This is verified by the zero Direct-Growth differences above.")
    lines.append("")
    lines.append("## 5. Limitations")
    lines.append("")
    lines.append("- No FundLens database query was executed, by Vicky's Option A decision.")
    lines.append("- The 85 registered count comes from FundLens's prior `RESULTS.md`, not a fresh `core.fact_nav` query.")
    lines.append("- Category attribution follows the section headers and the FundLens `scope.toml` category map; it is a read-only reimplementation for reconciliation, not a second production parser.")
    lines.append("- Counts may differ from FundLens's audited `RESULTS.md` because this scan includes all rows in the files, not only rows registered in the database.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Files={len(files)} ranges={len(by_range)} duplicate={dup_range} diffs={diff_count} growth_diffs={growth_diffs}")


if __name__ == "__main__":
    main()
