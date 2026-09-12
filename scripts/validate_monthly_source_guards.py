#!/usr/bin/env python3
"""Fail-closed source guards for one monthly territorial reconstruction.

The guard checks all Corsica station IDs across the requested month *and the immediately
preceding month used for month-over-month deltas* before eligibility filtering, and reuses C2's
production BDR perimeter guard across that same reconstruction window. A failure is written as
structured JSON before the process exits non-zero so diagnostics can be retained without weakening
the block.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_publication_state, load_bdr_categories, validate_recent_bdr_perimeter
from scripts.build_monthly_territorial import (
    load_c2_reference,
    load_geography,
    month_bounds,
    previous_month_bounds,
)
from scripts.build_v2_production_candidate import (
    BDR_REGISTRY, C1_META, C1_TAG, CORSE_REGISTRY, LEGACY_BDR, SWITCH_DAY,
    _bdr_category_resolver, _candidate_stale_bdr_ids, _evaluate_v2, _resolve_bdr,
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


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def unknown_bdr_details(window_state: pd.DataFrame) -> list[dict]:
    unknown = window_state[
        (window_state["territory"] == "Bouches-du-Rhone")
        & window_state["eligible_publication"]
        & window_state["category"].eq("unknown")
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
    output = ROOT / args.output
    start, end = month_bounds(args.month)
    prev_start, prev_end = previous_month_bounds(start)
    guard_start = prev_start
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
    observations, source = load_shared_observations(years, tag_prefix=args.tag_prefix, release_tag=release_tag)
    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy = load_bdr_categories(LEGACY_BDR)
    resolution = _resolve_bdr(observations, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver)
    stale_ids = _candidate_stale_bdr_ids(base_state, bouclier, SWITCH_DAY, end.date())
    resolution["stale_total_candidates"] = _resolve_stale_bdr_candidates(observations, stale_ids, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver)

    guards = EventGuards.from_release(release_tag, metadata=c1_meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    v2_state, engine = _evaluate_v2(
        base_state, bouclier=bouclier, event_guards=guards, corse_stations=corse_stations,
        start=SWITCH_DAY, end=end.date(),
    )

    # The generator uses both months. Guard exactly that complete reconstruction window, not only
    # the target month. This catches geography/perimeter problems that would otherwise affect the
    # reported month-over-month deltas without being seen by the preflight guard.
    window_state = v2_state[
        (v2_state["date"] >= guard_start)
        & (v2_state["date"] <= end)
        & v2_state["fuel"].isin(FUELS)
    ].copy()
    window_corse = window_state[window_state["territory"] == "Corse"]
    window_ids = set(window_corse["station_id"].astype(str).unique())
    geography_ids = set(geo["station_id"].astype(str).unique())
    missing = sorted(window_ids - geography_ids)

    base_result = {
        "schema": "a4c-monthly-source-guards-v2",
        "month": args.month,
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
        "previous_period_start": prev_start.strftime("%Y-%m-%d"),
        "previous_period_end": prev_end.strftime("%Y-%m-%d"),
        "guard_period_start": guard_start.strftime("%Y-%m-%d"),
        "guard_period_end": end.strftime("%Y-%m-%d"),
        "c1_release_tag": release_tag,
        "c2_reference_daily_target_end": c2_meta.get("daily_target_end"),
        "geography_rows": int(len(geo)),
        "epci_count": int(geo["epci_siren"].nunique()),
        "corsica_station_ids_checked_before_eligibility": len(window_ids),
        "r2_unavailable": engine.get("r2_unavailable"),
        "bdr_resolution": resolution,
    }

    if missing:
        details = []
        for sid in missing:
            g = window_corse[window_corse["station_id"].astype(str) == sid].sort_values("date")
            sample = g.iloc[-1]
            details.append({
                "station_id": sid,
                "cp": str(sample.get("cp", "")),
                "city": str(sample.get("city", "")),
                "address": str(sample.get("address", "")),
                "first_seen_in_guard_window": g["date"].min().strftime("%Y-%m-%d"),
                "last_seen_in_guard_window": g["date"].max().strftime("%Y-%m-%d"),
                "fuels": sorted(g["fuel"].astype(str).unique().tolist()),
                "eligible_fuels": sorted(g.loc[g["eligible_publication"], "fuel"].astype(str).unique().tolist()),
            })
        result = {
            **base_result,
            "status": "fail",
            "failure_kind": "missing_corsica_geography",
            "missing_geography": details,
            "unknown_recent_bdr_stations": [],
            "unknown_bdr_details": [],
        }
        write_result(output, result)
        raise SystemExit(2)

    bdr_details = unknown_bdr_details(window_state)
    try:
        unknown_bdr = validate_recent_bdr_perimeter(v2_state, since=guard_start)
    except RuntimeError as exc:
        result = {
            **base_result,
            "status": "fail",
            "failure_kind": "bdr_perimeter_incomplete",
            "failure_message": str(exc),
            "missing_geography": [],
            "unknown_recent_bdr_stations": [d["station_id"] for d in bdr_details],
            "unknown_bdr_details": bdr_details,
        }
        write_result(output, result)
        raise SystemExit(2)

    result = {
        **base_result,
        "status": "pass",
        "failure_kind": None,
        "missing_geography": [],
        "unknown_recent_bdr_stations": unknown_bdr,
        "unknown_bdr_details": bdr_details,
    }
    write_result(output, result)


if __name__ == "__main__":
    main()
