#!/usr/bin/env python3
import os, re, sys

ACCOUNTNAME = os.environ.get("ACCOUNTNAME")
if not ACCOUNTNAME:
    print("ERROR: set ACCOUNTNAME env var, e.g. ACCOUNTNAME='Jane#12345' python3 scripts/export_att_toys.py", file=sys.stderr)
    sys.exit(2)

path = f"/Applications/World of Warcraft/_retail_/WTF/Account/{ACCOUNTNAME}/SavedVariables/ATT_ToyTracker.lua"
with open(path, encoding="utf-8") as f:
    data = f.read()

def get_field(block, key):
    m = re.search(rf'{key}\s*=\s*"((?:\\.|[^"\\])*)"', block)
    return m.group(1) if m else ""

def get_bool(block, key):
    m = re.search(rf'{key}\s*=\s*(true|false)', block)
    return m.group(1) if m else None

def get_int(block, key):
    m = re.search(rf'{key}\s*=\s*(\d+)', block)
    return m.group(1) if m else ""


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


rows = []
for m in re.finditer(r"\[(\d+)\]\s*=\s*{(.*?)}\s*,", data, re.S):
    itemID = int(m.group(1))
    block = m.group(2)

    owned = get_bool(block, "owned")
    if owned is None:
        continue

    name = get_field(block, "name") or f"ItemID {itemID}"
    tier = get_int(block, "tierID")
    locs = get_field(block, "locations") or get_field(block, "location") or ""
    status = "OWNED" if owned == "true" else "MISSING"

    wowhead = wowhead_url(itemID)
    tomtom_cmds = parse_locations_for_tomtom(locs, name)
    tomtom_join = " | ".join(tomtom_cmds)

    sort_key = (0 if status == "MISSING" else 1, itemID)
    rows.append((sort_key, itemID, status, tier, name, locs, wowhead, tomtom_join))

rows.sort()

print("itemID,status,tierID,name,locations,wowhead_url,tomtom_commands")
for _, itemID, status, tier, name, locs, wowhead, tomtom in rows:
    def esc(s): return (s or "").replace('"','""')
    print(f'{itemID},{status},{tier},"{esc(name)}","{esc(locs)}","{esc(wowhead)}","{esc(tomtom)}"')
