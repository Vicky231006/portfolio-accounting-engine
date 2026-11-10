import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m0_reconcile_raw_files import RAW_DIR, parse_rows

files = sorted(RAW_DIR.rglob("*.gz"))
explicit_dg = 0
explicit_dg_unique = set()
any_dg = 0
for p in files:
    for code, d, nav, name, plan, option, cat, fields in parse_rows(p):
        if cat is None:
            continue
        plan_raw = fields[2].lower()
        option_raw = fields[3].lower()
        if "direct" in plan_raw and "growth" in option_raw:
            explicit_dg += 1
            explicit_dg_unique.add((code, d))
        if plan == "DIRECT" and option == "GROWTH":
            any_dg += 1
print("explicit plan+option DG rows", explicit_dg)
print("explicit plan+option DG unique", len(explicit_dg_unique))
print("derived DG rows", any_dg)
