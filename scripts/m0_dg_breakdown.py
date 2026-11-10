import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m0_reconcile_raw_files import RAW_DIR, parse_rows

files = sorted(RAW_DIR.rglob("*.gz"))
keys_2013 = set()
keys_all = set()
years = Counter()
for p in files:
    for code, d, nav, name, plan, option, cat, fields in parse_rows(p):
        if plan == "DIRECT" and option == "GROWTH" and cat is not None:
            keys_all.add((code, d))
            if d.year >= 2013:
                keys_2013.add((code, d))
            years[d.year] += 1
print("unique DG scope all", len(keys_all))
print("unique DG scope 2013+", len(keys_2013))
print("per-file rows by year (top/bottom):")
for y in sorted(years):
    print(y, years[y])
