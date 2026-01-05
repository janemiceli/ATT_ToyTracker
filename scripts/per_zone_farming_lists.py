#!/usr/bin/env python3
import os, re, sys, csv, pathlib
from collections import defaultdict

ACCOUNTNAME = os.environ.get("ACCOUNTNAME")
if not ACCOUNTNAME:
    print("ERROR: set ACCOUNTNAME env var, e.g. ACCOUNTNAME='Jane#12345' python3 scripts/per_zone_farming_lists.py", file=sys.stderr)
    sys.exit(2)

sv = f"/Applications/World of Warcraft/_retail_/WTF/Account/{ACCOUNTNAME}/SavedVariables/ATT_ToyTracker.lua"
data = pathlib.Path(sv).read_text(encoding="utf-8")

def get_field(block, key):
    m = re.search(rf'{key}\s*=\s*"((?:\\.|[^"\\])*)"', block)
    return m.group(1) if m else ""

def get_bool(block, key):
    m = re.search(rf'{key}\s*=\s*(true|false)', block)
    return m.group(1) if m else None

def get_int(block, key):
    m = re.search(rf'{key}\s*=\s*(\d+)', block)
    return int(m.group(1)) if m else None


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
    # "12.3, 45.6 — Zone Name (1234)" OR "Zone Name (1234)"
    if "—" in loc:
        right = loc.split("—", 1)[1].strip()
    else:
        right = loc.strip()
    right = re.sub(r"\s*\(\d+\)\s*$", "", right).strip()
    return right or "Unknown"

zones = defaultdict(list)

for m in re.finditer(r"\[(\d+)\]\s*=\s*{(.*?)}\s*,", data, re.S):
    itemID = int(m.group(1))
    block = m.group(2)

    owned = get_bool(block, "owned")
    if owned != "false":
        continue  # only missing

    name = get_field(block, "name") or f"ItemID {itemID}"
    locs = get_field(block, "locations") or get_field(block, "location") or "Unknown"
    tier = get_int(block, "tierID") or ""
    url = wowhead_url(itemID)
    tomtom_join = " | ".join(parse_locations_for_tomtom(locs, name))

    loc_list = [s.strip() for s in locs.split(";") if s.strip()] if locs else ["Unknown"]
    for loc in loc_list:
        z = zone_from_location(loc)
        zones[z].append((name, itemID, tier, loc, url, tomtom_join))

for z in zones:
    zones[z].sort(key=lambda x: (x[0].lower(), x[1]))

out_dir = pathlib.Path(__file__).resolve().parent.parent / "output"
out_dir.mkdir(parents=True, exist_ok=True)

md_path = out_dir / "missing_toys_by_zone.md"
csv_path = out_dir / "missing_toys_by_zone.csv"

with md_path.open("w", encoding="utf-8") as f:
    f.write("# Missing Toys by Zone (best-effort)\n\n")
    f.write("> Generated from ATT_ToyTracker SavedVariables. Locations + TomTom commands are best-effort.\n\n")
    for zone in sorted(zones.keys(), key=lambda s: s.lower()):
        f.write(f"## {zone}\n\n")
        f.write("| Toy | itemID | tierID | Location | TomTom |\n")
        f.write("|---|---:|---:|---|---|\n")
        seen=set()
        for name, itemID, tier, loc, url, tomtom in zones[zone]:
            if itemID in seen:
                continue
            seen.add(itemID)
            safe_loc = loc.replace("|", "\\|")
            safe_name = name.replace("|", "\\|")
            tt = f"`{tomtom}`" if tomtom else ""
            f.write(f"| [{safe_name}]({url}) | {itemID} | {tier} | {safe_loc} | {tt} |\n")
        f.write("\n")

with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["zone","toy_name","itemID","tierID","location","wowhead_url","tomtom_commands"])
    for zone in sorted(zones.keys(), key=lambda s: s.lower()):
        seen=set()
        for name, itemID, tier, loc, url, tomtom in zones[zone]:
            if itemID in seen:
                continue
            seen.add(itemID)
            w.writerow([zone, name, itemID, tier, loc, url, tomtom])

print(f"Wrote: {md_path}")
print(f"Wrote: {csv_path}")
