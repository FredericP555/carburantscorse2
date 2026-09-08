#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories
from scripts.build_v2_production_candidate import (
    LEGACY_BDR, BDR_REGISTRY, C1_META, C1_TAG, CORSE_REGISTRY,
    _bdr_category_resolver, _evaluate_v2,
)
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

DAY = date(2026, 8, 24)
HISTORICAL = "a4c-v2-shared-20260824T232328Z-32788829663"
LATEST = "a4c-v2-shared-20260908T011056Z-34175476841"


def published_rows() -> dict:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    out = {}
    for ref, bdr_fuel in (("sp95", "SP95"), ("e10", "E10")):
        for scope, group in (("all", "all"), ("network", "reseau")):
            rows = data["DATA"]["sp95"][ref]["daily"][group]
            row = next(r for r in rows if str(r["date"]) == DAY.isoformat())
            out[f"{ref}/{scope}"] = deepcopy(row)
    return out


def recompute(tag: str) -> dict:
    shutil.rmtree(ROOT / "outputs" / "c1", ignore_errors=True)
    shutil.rmtree(ROOT / "outputs" / "ufip", ignore_errors=True)
    (ROOT / "outputs" / "c1").mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "ufip").mkdir(parents=True, exist_ok=True)

    download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix="a4c-v2-shared-",
        release_tag=tag,
        registry_output=CORSE_REGISTRY,
        tag_output=C1_TAG,
    )
    meta = json.loads(C1_META.read_text(encoding="utf-8"))
    years = sorted(int(y) for y in meta.get("years", []))
    observations, source = load_shared_observations(
        years,
        tag_prefix="a4c-v2-shared-",
        release_tag=tag,
    )
    source_max = date.fromisoformat(str(source["shared_source_max_date"]))
    assert source_max >= DAY, (tag, source_max)

    legacy = load_bdr_categories(LEGACY_BDR)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(DAY),
        bdr_category_resolver=resolver,
    )
    bouclier = source.get("bouclier") or meta.get("bouclier")
    guards = EventGuards.from_release(tag, metadata=meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    v2_state, engine = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=DAY,
        end=DAY,
    )

    out = {"tag": tag, "source_max": source_max.isoformat(), "engine": engine, "rows": {}}
    for ref, bdr_fuel in (("sp95", "SP95"), ("e10", "E10")):
        for scope, group in (("all", "all"), ("network", "reseau")):
            rows = build_gap_series(
                v2_state,
                corsica_fuel="SP95",
                bdr_fuel=bdr_fuel,
                bdr_scope=scope,
                granularity="daily",
            )
            row = next(r for r in rows if str(r["date"]) == DAY.isoformat())
            out["rows"][f"{ref}/{scope}"] = row
    return out


def main() -> None:
    published = published_rows()
    historical = recompute(HISTORICAL)
    latest = recompute(LATEST)
    result = {"published": published, "historical_release": historical, "latest_release": latest, "comparison": {}}
    for key in published:
        p = published[key]
        h = historical["rows"][key]
        l = latest["rows"][key]
        result["comparison"][key] = {
            "published_ecart": p.get("ecart"),
            "historical_ecart": h.get("ecart"),
            "latest_ecart": l.get("ecart"),
            "historical_minus_published_c_l": round(float(h["ecart"]) - float(p["ecart"]), 6),
            "latest_minus_published_c_l": round(float(l["ecart"]) - float(p["ecart"]), 6),
            "historical_row": h,
            "latest_row": l,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
