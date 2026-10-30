#!/usr/bin/env python3
"""Read-only audit of three historical BdR station IDs in validated C1 official declarations."""
import json
from collections import defaultdict
from a4c_common.shared_release import load_shared_observations

IDS = ("13120001", "13530003", "13740003")
TAG = "a4c-v2-shared-20261026T162416Z-40357791719"
rows, source = load_shared_observations([2025, 2026], release_tag=TAG, tag_prefix="a4c-v2-shared-")
report = {"release_tag": TAG, "max_official_date": source["shared_source_max_date"], "stations": {}}
for sid in IDS:
    matches = [r for r in rows if str(r["station_id"]) == sid]
    matches.sort(key=lambda r: (r["timestamp"], r["fuel"]))
    by_fuel = defaultdict(list)
    for x in matches:
        by_fuel[x["fuel"]].append(x)
    def compact(r):
        return {
            "date": r["date"].isoformat(),
            "timestamp": r["timestamp"].isoformat(),
            "fuel": r["fuel"], "price_eur_l": r["price"],
            "department": r["department"], "cp": r["cp"],
            "city": r["city"], "address": r["address"],
            "is_motorway": r["is_motorway"], "pop": r["pop"],
            "latitude": r["latitude"], "longitude": r["longitude"],
        }
    report["stations"][sid] = {
        "count_2025_2026": len(matches),
        "first_in_snapshot": compact(matches[0]) if matches else None,
        "last_in_snapshot": compact(matches[-1]) if matches else None,
        "last_by_fuel": {fuel: compact(vals[-1]) for fuel, vals in sorted(by_fuel.items())},
        "years_count": {str(y): sum(x["source_year"] == y for x in matches) for y in (2025, 2026)},
        "unique_addresses": sorted({(r["cp"], r["city"], r["address"]) for r in matches}),
    }

# Search for 2026 official stations at the same site/very nearby, which could
# indicate a change of identifier (not proof of change of operator).
import math
import re

def point(record):
    try:
        return float(record["latitude"]) / 100000, float(record["longitude"]) / 100000
    except (TypeError, ValueError):
        return None

def distance_m(a, b):
    if not a or not b:
        return None
    p1, g1 = map(math.radians, a)
    p2, g2 = map(math.radians, b)
    x = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin((g2-g1)/2)**2
    return round(12742000 * math.asin(min(1, math.sqrt(x))))

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

latest_2026 = {}
for r in rows:
    if r["source_year"] != 2026 or r["department"] != "13":
        continue
    sid = str(r["station_id"])
    if sid not in latest_2026 or r["timestamp"] > latest_2026[sid]["timestamp"]:
        latest_2026[sid] = r

for sid in IDS:
    target = next((r for r in rows if r["station_id"] == sid), None)
    if target is None:
        continue
    close = []
    exact = []
    for other_id, candidate in latest_2026.items():
        if other_id == sid:
            continue
        dist = distance_m(point(target), point(candidate))
        record = {
            "id": other_id, "cp": candidate["cp"], "city": candidate["city"],
            "address": candidate["address"],
            "distance_m": dist, "last_observation": candidate["date"].isoformat()
        }
        if (norm(target["address"]) == norm(candidate["address"]) and
                norm(target["city"]) == norm(candidate["city"])):
            exact.append(record)
        if dist is not None and dist < 2000:
            close.append(record)
    report["stations"][sid]["same_normalized_address_2026"] = sorted(exact, key=lambda x: x["id"])
    report["stations"][sid]["nearest_2026_within_2km"] = sorted(close, key=lambda x: x["distance_m"])[:8]


CANDIDATES = ("13120012", "13120008", "13530004", "13530001", "13740001", "13740004")
report["nearby_ids_year_coverage"] = {}
for cid in CANDIDATES:
    o = sorted((r for r in rows if r["station_id"] == cid), key=lambda r: r["timestamp"])
    yr2025 = [r for r in o if r["source_year"] == 2025]
    yr2026 = [r for r in o if r["source_year"] == 2026]
    report["nearby_ids_year_coverage"][cid] = {
        "total_count": len(o),
        "count_2025": len(yr2025), "count_2026": len(yr2026),
        "first_2025": compact(yr2025[0]) if yr2025 else None,
        "last_2025": compact(yr2025[-1]) if yr2025 else None,
        "first_2026": compact(yr2026[0]) if yr2026 else None,
    }

print("OFFICIAL_STATION_HISTORY_JSON_START", flush=True)
print(json.dumps(report, ensure_ascii=False, default=list, indent=2), flush=True)
print("OFFICIAL_STATION_HISTORY_JSON_END", flush=True)
