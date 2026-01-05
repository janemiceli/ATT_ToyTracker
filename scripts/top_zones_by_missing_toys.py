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


def parse_locations_for_tomtom(locs: str, toy_name: str):
    # loc format from addon: "12.3, 45.6 — Zone Name (1234); 10.0, 20.0 — Another Zone (5678); Zone Name (999)"
    cmds = []
    if not locs:
        return cmds
    parts = [p.strip() for p in locs.split(";") if p.strip()]
    for p in parts:
        m = re.match(r'^(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*—.*\((\d+)\)\s*$', p)
        if m:
            x, y, mapid = m.group(1), m.group(2), m.group(3)
            # TomTom supports: /way #<mapID> <x> <y> <title>
            cmds.append(f"/way #{mapid} {x} {y} {toy_name}")
    return cmds

def wowhead_url(itemID: int) -> str:
    return f"https://www.wowhead.com/item={itemID}"


def zone_from_location(loc: str) -> str:
    if not loc:
        return "Unknown"
    if "—" in loc:
        loc = loc.split("—", 1)[1]
    loc = re.sub(r"\s*\(\d+\)\s*$", "", loc).strip()
    return loc or "Unknown"

zone_items = defaultdict(set)
zone_entries = defaultdict(dict)  # zone -> itemID -> (name, url, tomtom)

for m in re.finditer(r"\[(\d+)\]\s*=\s*{(.*?)}\s*,", data, re.S):
    itemID = int(m.group(1))
    block = m.group(2)

    owned = get_bool(block, "owned")
    if owned != "false":
        continue

    name = get_field(block, "name") or f"ItemID {itemID}"
    locs = get_field(block, "locations") or get_field(block, "location") or "Unknown"
    loc_list = [s.strip() for s in locs.split(";") if s.strip()] if locs else ["Unknown"]

    url = wowhead_url(itemID)
    tomtom_join = " | ".join(parse_locations_for_tomtom(locs, name))

    zones_seen=set()
    for loc in loc_list:
        zone = zone_from_location(loc)
        zones_seen.add(zone)
        zone_entries[zone].setdefault(itemID, (name, url, tomtom_join))

    for zone in zones_seen:
        zone_items[zone].add(itemID)

summary = sorted(((len(v), k) for k,v in zone_items.items()), key=lambda x: (-x[0], x[1].lower()))

out_dir = pathlib.Path(__file__).resolve().parent.parent / "output"
out_dir.mkdir(exist_ok=True)

md = out_dir / "top_zones_by_missing_toys.md"
csvf = out_dir / "top_zones_by_missing_toys.csv"

with md.open("w", encoding="utf-8") as f:
    f.write("# Top Zones by Missing Toy Count (best-effort)\n\n")
    f.write("| Rank | Zone | Missing Toys |\n|---:|---|---:|\n")
    for i,(count,zone) in enumerate(summary,1):
        f.write(f"| {i} | {zone} | {count} |\n")

    f.write("\n## Quick drill-down (top 10 zones)\n\n")
    for count, zone in summary[:10]:
        f.write(f"### {zone} ({count})\n\n")
        items = sorted(zone_entries.get(zone, {}).items(), key=lambda kv: kv[1][0].lower())
        for itemID, (name, url, tomtom) in items:
            safe_name = name.replace("|", "\\|")
            tt = f" — `{tomtom}`" if tomtom else ""
            f.write(f"- [{safe_name}]({url}) (itemID {itemID}){tt}\n")
        f.write("\n")

with csvf.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank","zone","missing_toy_count"])
    for i,(count,zone) in enumerate(summary,1):
        w.writerow([i,zone,count])

print("Wrote:", md)
print("Wrote:", csvf)
