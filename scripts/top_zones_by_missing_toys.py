#!/usr/bin/env python3
import os, re, sys, csv, pathlib
from collections import defaultdict

ACCOUNTNAME = os.environ.get("ACCOUNTNAME")
if not ACCOUNTNAME:
    print("ERROR: set ACCOUNTNAME env var, e.g. ACCOUNTNAME='Jane#12345' python3 scripts/top_zones_by_missing_toys.py", file=sys.stderr)
    sys.exit(2)

sv = f"/Applications/World of Warcraft/_retail_/WTF/Account/{ACCOUNTNAME}/SavedVariables/ATT_ToyTracker.lua"
data = pathlib.Path(sv).read_text(encoding="utf-8")

def get_field(block, key):
    m = re.search(rf'{key}\s*=\s*"((?:\\.|[^"\\])*)"', block)
    return m.group(1) if m else ""

def get_bool(block, key):
    m = re.search(rf'{key}\s*=\s*(true|false)', block)
    return m.group(1) if m else None

def zone_from_location(loc: str) -> str:
    if not loc:
        return "Unknown"
    if "—" in loc:
        loc = loc.split("—", 1)[1]
    loc = re.sub(r"\s*\(\d+\)\s*$", "", loc).strip()
    return loc or "Unknown"

zone_items = defaultdict(set)

for m in re.finditer(r"\[(\d+)\]\s*=\s*{(.*?)}\s*,", data, re.S):
    itemID = int(m.group(1))
    block = m.group(2)
    owned = get_bool(block, "owned")
    if owned != "false":
        continue
    locs = get_field(block, "locations") or get_field(block, "location") or "Unknown"
    for loc in [s.strip() for s in locs.split(";") if s.strip()]:
        zone = zone_from_location(loc)
        zone_items[zone].add(itemID)

summary = sorted(((len(v), k) for k,v in zone_items.items()), reverse=True)

out_dir = pathlib.Path(__file__).resolve().parent.parent / "output"
out_dir.mkdir(exist_ok=True)

md = out_dir / "top_zones_by_missing_toys.md"
csvf = out_dir / "top_zones_by_missing_toys.csv"

with md.open("w", encoding="utf-8") as f:
    f.write("# Top Zones by Missing Toy Count\n\n")
    f.write("| Rank | Zone | Missing Toys |\n|---:|---|---:|\n")
    for i,(count,zone) in enumerate(summary,1):
        f.write(f"| {i} | {zone} | {count} |\n")

with csvf.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank","zone","missing_toy_count"])
    for i,(count,zone) in enumerate(summary,1):
        w.writerow([i,zone,count])

print("Wrote:", md)
print("Wrote:", csvf)
