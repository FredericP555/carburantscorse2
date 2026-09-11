#!/usr/bin/env python3
"""Fail-closed source guards for one monthly territorial reconstruction.

This script intentionally runs before any monthly output is promoted from the isolated workdir.
It checks *all* Corsica station IDs present in the target month before eligibility filtering and
reuses C2's production BDR perimeter guard on the V2-evaluated month.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import (
    build_publication_state,
    load_bdr_categories,
    validate_recent_bdr_perimeter,
)
from scripts.build_monthly_territorial import load_c2_reference, load_geography, month_bounds
from scripts.build_v2_production_candidate import (
    BDR_REGISTRY,
    C1_META,
    C1_TAG,
    CORSE_REGISTRY,
    LEGACY_BDR,
    SWITCH_DAY,
    _bdr_category_resolver,
    _candidate_stale_bdr_ids,
    _evaluate_v2,
    _resolve_bdr,
    _resolve_stale_bdr_candidates,
)
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

ROOT = Path(__file__).resolve().parents[1]
FUELS = ("Gazole", "SP95")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True)
    p.add_argument("--geography", default="config/corse_station_geography_2026.csv")
    p.add_argument("--c2-data", default="data.json")
    p.add_argument("--release-tag")
    p.add_argument("--tag-prefix", default="a4c-v2-shared-")
    p.add_argument("--output", required=True)
    return p.parse_args()


def unknown_bdr_details(month_state: pd.DataFrame) -> list[dict]:
    unknown = month_state[
        (month_state["territory"] == "Bouches-du-Rhone")
        & month_state["eligible_publication"]
        & month_state["category"].eq("unknown")
    ].copy()
    details: list[dict] = []
    for sid, group in unknown.groupby("station_id", sort=True):
        group = group.sort_values("date")
        sample = group.iloc[-1]
        dates = group["date"].dt.strftime("%Y-%m-%d")
        source_ts = pd.to_datetime(group.get("source_timestamp"), errors="coerce")
        details.append({
            "station_id": str(sid),
            "cp": str(sample.get("cp", "")),
            "city": str(sample.get("city", "")),
            "address": str(sample.get("address", "")),
            "first_eligible_unknown_day": str(dates.min()),
            "last_eligible_unknown_day": str(dates.max()),
            "eligible_unknown_station_days": int(len(group)),
            "fuels": sorted(group["fuel"].astype(str).unique().tolist()),
            "source_timestamp_min": None if source_ts.isna().all() else source_ts.min().isoformat(),
            "source_timestamp_max": None if source_ts.isna().all() else source_ts.max().isoformat(),
        })
    return details


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("Requested month is not complete")

    geo = load_geography(ROOT / args.geography)
    c2_path = Path(args.c2_data)
    if not c2_path.is_absolute():
        c2_path = ROOT / c2_path
    c2_meta, c2_release_tag = load_c2_reference(c2_path, end)
    release_tag = args.release_tag or c2_release_tag
    if release_tag != c2_release_tag:
        raise RuntimeError("Explicit C1 release does not match C2 pinned release")

    download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix=args.tag_prefix,
        release_tag=release_tag,
        registry_output=CORSE_REGISTRY,
        tag_output=C1_TAG,
    )
    c1_meta = json.loads(C1_META.read_text(encoding="utf-8"))
    years = sorted(int(y) for y in c1_meta.get("years", []))
    observations, source = load_shared_observations(
        years,
        tag_prefix=args.tag_prefix,
        release_tag=release_tag,
    )
    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy = load_bdr_categories(LEGACY_BDR)
    resolution = _resolve_bdr(observations, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(
        pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver
    )
    stale_ids = _candidate_stale_bdr_ids(base_state, bouclier, SWITCH_DAY, end.date())
    resolution["stale_total_candidates"] = _resolve_stale_bdr_candidates(observations, stale_ids, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(
        pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver
    )

    guards = EventGuards.from_release(release_tag, metadata=c1_meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    v2_state, engine = _evaluate_v2(
        base_state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end.date(),
    )

    month_state = v2_state[
        (v2_state["date"] >= start)
        & (v2_state["date"] <= end)
        & v2_state["fuel"].isin(FUELS)
    ].copy()
    month_corse = month_state[month_state["territory"] == "Corse"]
    month_ids = set(month_corse["station_id"].astype(str).unique())
    geography_ids = set(geo["station_id"].astype(str).unique())
    missing = sorted(month_ids - geography_ids)
    if missing:
        details = []
        for sid in missing:
            g = month_corse[month_corse["station_id"].astype(str) == sid].sort_values("date")
            sample = g.iloc[-1]
            details.append({
                "station_id": sid,
                "cp": str(sample.get("cp", "")),
                "city": str(sample.get("city", "")),
                "address": str(sample.get("address", "")),
                "fuels": sorted(g["fuel"].astype(str).unique().tolist()),
                "eligible_fuels": sorted(g.loc[g["eligible_publication"], "fuel"].astype(str).unique().tolist()),
            })
        raise RuntimeError(
            "Monthly geography incomplete before eligibility filtering: "
            + json.dumps(details, ensure_ascii=False)
        )

    # Exact production guard, applied to the entire period being recalculated. Do not downgrade
    # this to a warning: if it fails, a network-scope monthly comparison is not reproducible yet.
    bdr_details = unknown_bdr_details(month_state)
    try:
        unknown_bdr = validate_recent_bdr_perimeter(v2_state, since=start)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}; monthly_unknown_details="
            + json.dumps(bdr_details, ensure_ascii=False)
        ) from exc

    result = {
        "schema": "a4c-monthly-source-guards-v1",
        "status": "pass",
        "month": args.month,
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
        "c1_release_tag": release_tag,
        "c2_reference_daily_target_end": c2_meta.get("daily_target_end"),
        "geography_rows": int(len(geo)),
        "epci_count": int(geo["epci_siren"].nunique()),
        "corsica_station_ids_checked_before_eligibility": len(month_ids),
        "missing_geography": missing,
        "unknown_recent_bdr_stations": unknown_bdr,
        "unknown_bdr_details": bdr_details,
        "r2_unavailable": engine.get("r2_unavailable"),
        "bdr_resolution": resolution,
    }
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
