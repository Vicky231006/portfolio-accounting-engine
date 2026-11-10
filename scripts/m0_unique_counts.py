import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m0_reconcile_raw_files import RAW_DIR, parse_rows

files = sorted(RAW_DIR.rglob("*.gz"))
all_keys = set()
dg_keys = set()
dg_scope_keys = set()
all_rows = 0
for p in files:
    for code, d, nav, name, plan, option, cat, fields in parse_rows(p):
        all_rows += 1
        all_keys.add((code, d))
        if plan == "DIRECT" and option == "GROWTH":
            dg_keys.add((code, d))
            if cat is not None:
                dg_scope_keys.add((code, d))
print("rows", all_rows)
print("unique all", len(all_keys))
print("unique DG", len(dg_keys))
print("unique DG scope", len(dg_scope_keys))
