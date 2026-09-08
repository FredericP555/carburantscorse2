#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories
from scripts import v2_event_guards
from scripts.build_v2_production_candidate import (
    BDR_REGISTRY,
    LEGACY_BDR,
    SWITCH_DAY,
    _bdr_category_resolver,
    _evaluate_v2,
)
from scripts.resolve_new_bdr_station_brands import load_registry

ROOT = Path(__file__).resolve().parents[1]
TARGET = date(2026, 8, 24)
OLD_TAG = "a4c-v2-shared-20260824T232328Z-32788829663"
CURRENT_TAG = "a4c-v2-shared-20260908T011056Z-34175476841"
PREFIX = "a4c-v2-shared-"


def frozen_rows():
    payload = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    found = []

    def walk(obj, path=()):
        if isinstance(obj, dict):
            if obj.get("date") == TARGET.isoformat() and "ecart" in obj:
                found.append(("/".join(map(str, path)), dict(obj)))
            for key, value in obj.items():
                walk(value, path + (key,))
        elif isinstance(obj, list):
            for index, value in enumerate(obj):
                walk(value, path + (index,))

    walk(payload)
    return found


def recompute(tag: str, label: str):
    audit_root = ROOT / "outputs" / "audit-h02" / label
    registry_path = audit_root / "corse_station_brands.json"
    tag_path = audit_root / "shared_release_tag.txt"
    download_shared_rotterdam_assets(
        audit_root,
        tag_prefix=PREFIX,
        release_tag=tag,
        registry_output=registry_path,
        tag_output=tag_path,
    )
    meta = json.loads((audit_root / "c1_shared_meta.json").read_text(encoding="utf-8"))
    years = sorted(int(y) for y in meta.get("years", []))
    observations, source = load_shared_observations(years, tag_prefix=PREFIX, release_tag=tag)

    legacy = load_bdr_categories(LEGACY_BDR)
    resolver = _bdr_category_resolver(legacy, load_registry(BDR_REGISTRY))
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(TARGET),
        bdr_category_resolver=resolver,
    )
    bouclier = source.get("bouclier") or meta.get("bouclier")
    corse_stations = json.loads(registry_path.read_text(encoding="utf-8"))["stations"]
    guards = v2_event_guards.EventGuards.from_release(tag, metadata=meta)
    state, evaluation = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=TARGET,
    )

    outputs = {}
    for bdr_fuel in ("SP95", "E10"):
        for scope in ("all", "network"):
            rows = build_gap_series(
                state,
                corsica_fuel="SP95",
                bdr_fuel=bdr_fuel,
                bdr_scope=scope,
                granularity="daily",
                include_levels=True,
            )
            row = next(r for r in rows if r["date"] == TARGET.isoformat())
            outputs[f"SP95_vs_{bdr_fuel}_{scope}"] = row

    day = state[state["date"].dt.date == TARGET].copy()
    day = day[
        ((day["territory"] == "Corse") & (day["fuel"] == "SP95"))
        | ((day["territory"] == "Bouches-du-Rhone") & day["fuel"].isin(["SP95", "E10"]))
    ]
    sample = {}
    for r in day.itertuples(index=False):
        key = (str(r.territory), str(r.fuel), str(r.station_id))
        sample[key] = {
            "price": None if pd.isna(r.price) else float(r.price),
            "price_ht": None if pd.isna(r.price_ht) else float(r.price_ht),
            "category": str(r.category),
            "eligible": bool(r.eligible_publication),
            "source_timestamp": None if pd.isna(r.source_timestamp) else str(pd.Timestamp(r.source_timestamp)),
        }

    return {
        "tag": tag,
        "source_sha256": source.get("sha256"),
        "source_max_date": source.get("shared_source_max_date"),
        "outputs": outputs,
        "sample": sample,
        "evaluation": evaluation,
    }


def main():
    frozen = frozen_rows()
    print("=== FROZEN C2 ROWS ON 2026-08-24 ===")
    for path, row in frozen:
        print(path, json.dumps(row, ensure_ascii=False, sort_keys=True))

    old = recompute(OLD_TAG, "old")
    current = recompute(CURRENT_TAG, "current")

    print("=== RECOMPUTED FOUR SP95 GAPS ===")
    for key in old["outputs"]:
        print(key, "old=", old["outputs"][key], "current=", current["outputs"][key])

    print("=== SOURCE METADATA ===")
    print("old", old["tag"], old["source_sha256"], old["source_max_date"])
    print("current", current["tag"], current["source_sha256"], current["source_max_date"])

    print("=== STATION-DAY DIFFERENCES ON TARGET DAY ===")
    keys = sorted(set(old["sample"]) | set(current["sample"]))
    diffs = []
    for key in keys:
        before = old["sample"].get(key)
        after = current["sample"].get(key)
        if before != after:
            diffs.append((key, before, after))
            print(key, "OLD=", before, "CURRENT=", after)
    print("station_day_diff_count=", len(diffs))

    out = {
        "target_date": TARGET.isoformat(),
        "frozen_rows": [{"path": p, "row": r} for p, r in frozen],
        "old": {k: v for k, v in old.items() if k != "sample"},
        "current": {k: v for k, v in current.items() if k != "sample"},
        "station_day_differences": [
            {"territory": k[0], "fuel": k[1], "station_id": k[2], "old": b, "current": a}
            for k, b, a in diffs
        ],
    }
    out_path = ROOT / "outputs" / "audit-h02" / "result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
