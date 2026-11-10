import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m0_reconcile_raw_files import RAW_DIR, parse_rows

files = sorted(RAW_DIR.rglob("*.gz"))
per_file = Counter()
unique = set()
for p in files:
    for code, d, nav, name, plan, option, cat, fields in parse_rows(p):
        if plan == "DIRECT" and option == "GROWTH" and cat is not None:
            per_file[cat] += 1
            unique.add((code, d, cat))
print("per-file by category")
for k, v in per_file.most_common():
    print(k, v)
print("total", sum(per_file.values()))
print("unique (code,date,cat)", len(unique))
