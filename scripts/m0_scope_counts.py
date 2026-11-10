import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m0_reconcile_raw_files import RAW_DIR, parse_rows

files = sorted(RAW_DIR.rglob("*.gz"))
per_file_all = 0
per_file_dg = 0
per_file_rg = 0
unique_all = set()
unique_dg = set()
unique_rg = set()
plans = Counter()
options = Counter()
for p in files:
    for code, d, nav, name, plan, option, cat, fields in parse_rows(p):
        if cat is None:
            continue
        per_file_all += 1
        unique_all.add((code, d))
        plans[plan] += 1
        options[option] += 1
        if plan == "DIRECT" and option == "GROWTH":
            per_file_dg += 1
            unique_dg.add((code, d))
        if plan == "REGULAR" and option == "GROWTH":
            per_file_rg += 1
            unique_rg.add((code, d))
print("per_file_all_in_scope", per_file_all)
print("unique_all_in_scope", len(unique_all))
print("per_file_direct_growth", per_file_dg)
print("unique_direct_growth", len(unique_dg))
print("per_file_regular_growth", per_file_rg)
print("unique_regular_growth", len(unique_rg))
print("plans", plans)
print("options", options)
