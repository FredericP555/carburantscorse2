#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from a4c_common import shared_release
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
REPOSITORY = "FredericP555/carburantscorse1"


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


def raw_release(tag: str):
    """Read one immutable historical C1 release as published, not through today's stricter contract.

    We still validate the historical snapshot bytes against that release's own manifest and decode
    the manifest semantically. This avoids falsely rejecting the 24-Aug release only because later
    C1 contracts added Rotterdam metadata fields that did not exist yet.
    """
    release_url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}"
    release = shared_release._request_json(release_url)
    if str(release.get("tag_name") or "") != tag or release.get("draft"):
        raise RuntimeError(f"Historical release lookup mismatch: {tag}")

    meta_bytes = shared_release._request_bytes(shared_release._asset_url(release, shared_release.META_ASSET))
    meta = json.loads(meta_bytes.decode("utf-8"))
    if meta.get("schema") != shared_release.SCHEMA:
        raise RuntimeError(f"Unexpected historical snapshot schema: {meta.get('schema')!r}")

    data_bytes = shared_release._request_bytes(shared_release._asset_url(release, shared_release.DATA_ASSET), timeout=180)
    years = sorted(int(y) for y in meta.get("years", []))
    observations = shared_release._decode_snapshot(data_bytes, meta, years)

    brands_bytes = shared_release._request_bytes(shared_release._asset_url(release, shared_release.CORSE_BRANDS_ASSET))
    brands = json.loads(brands_bytes.decode("utf-8"))
    if brands.get("schema") != shared_release.CORSE_BRANDS_SCHEMA:
        raise RuntimeError(f"Unexpected Corsica-brand schema in {tag}: {brands.get('schema')!r}")

    source = {
        "sha256": meta.get("sha256"),
        "shared_source_max_date": meta.get("max_date"),
        "bouclier": meta.get("bouclier"),
    }
    return release, meta, observations, brands, source


def recompute(tag: str):
    _release, meta, observations, brands, source = raw_release(tag)

    legacy = load_bdr_categories(LEGACY_BDR)
    resolver = _bdr_category_resolver(legacy, load_registry(BDR_REGISTRY))
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(TARGET),
        bdr_category_resolver=resolver,
    )
    bouclier = source.get("bouclier") or meta.get("bouclier")
    guards = v2_event_guards.EventGuards.from_release(tag, metadata=meta)
    state, evaluation = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=brands["stations"],
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


def relevant_frozen(frozen):
    wanted = {
        "DATA/sp95/sp95/daily/all": "SP95_vs_SP95_all",
        "DATA/sp95/sp95/daily/reseau": "SP95_vs_SP95_network",
        "DATA/sp95/e10/daily/all": "SP95_vs_E10_all",
        "DATA/sp95/e10/daily/reseau": "SP95_vs_E10_network",
    }
    out = {}
    for path, row in frozen:
        for prefix, key in wanted.items():
            if path.startswith(prefix + "/"):
                out[key] = row
    return out


def main():
    frozen = frozen_rows()
    frozen4 = relevant_frozen(frozen)
    print("=== FROZEN FOUR C2 SP95 ROWS ON 2026-08-24 ===")
    for key, row in frozen4.items():
        print(key, json.dumps(row, ensure_ascii=False, sort_keys=True))

    old = recompute(OLD_TAG)
    current = recompute(CURRENT_TAG)

    print("=== RECOMPUTED FOUR SP95 GAPS ===")
    for key in old["outputs"]:
        print(key, "frozen=", frozen4.get(key), "old=", old["outputs"][key], "current=", current["outputs"][key])

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
        "frozen_four": frozen4,
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
