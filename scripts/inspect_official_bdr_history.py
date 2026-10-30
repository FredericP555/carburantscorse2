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
print("OFFICIAL_STATION_HISTORY_JSON_START", flush=True)
print(json.dumps(report, ensure_ascii=False, default=list, indent=2), flush=True)
print("OFFICIAL_STATION_HISTORY_JSON_END", flush=True)
