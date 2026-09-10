#!/usr/bin/env python3
"""Audit territorial representativity without changing C2 or ranking rules.

For every Corsican EPCI/fuel, compare the station-days retained by the current C2 V2
eligibility engine with the wider set of geography-registry stations that have declared the
fuel at least once by the end of the requested month. This is diagnostic only: it does not
modify build_monthly_territorial.py, data.json, or WordPress.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_publication_state, load_bdr_categories
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
    p.add_argument("--markdown")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("Requested month is not complete")
    if start.date() < SWITCH_DAY:
        raise RuntimeError("This audit is intended for C2 V2 months")

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
    _resolve_bdr(observations, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(
        pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver
    )
    stale_ids = _candidate_stale_bdr_ids(base_state, bouclier, SWITCH_DAY, end.date())
    _resolve_stale_bdr_candidates(observations, stale_ids, legacy)
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
        start=start.date(),
        end=end.date(),
    )

    obs = pd.DataFrame(observations)
    obs["station_id"] = obs["station_id"].astype(str)
    obs["fuel"] = obs["fuel"].astype(str)
    obs["department"] = obs["department"].astype(str)
    obs["date"] = pd.to_datetime(obs["date"]).dt.normalize()
    obs = obs[(obs["department"] == "20") & (obs["date"] <= end) & obs["fuel"].isin(FUELS)].copy()
    fuel_stations = set(zip(obs["station_id"], obs["fuel"]))

    month_state = v2_state[
        (v2_state["territory"] == "Corse")
        & (v2_state["date"] >= start)
        & (v2_state["date"] <= end)
        & v2_state["fuel"].isin(FUELS)
    ].copy()
    month_state = month_state.merge(
        geo[["station_id", "epci_siren", "epci_nom", "commune", "localite"]],
        on="station_id", how="left", validate="many_to_one"
    )

    missing_geography: list[dict] = []
    missing_mask = month_state["epci_siren"].isna()
    if missing_mask.any():
        missing_state = month_state[missing_mask].copy()
        for sid, group in missing_state.groupby("station_id", sort=True):
            sample = group.sort_values("date").iloc[-1]
            missing_geography.append({
                "station_id": str(sid),
                "cp": str(sample.get("cp", "")),
                "city": str(sample.get("city", "")),
                "address": str(sample.get("address", "")),
                "latitude": None if pd.isna(sample.get("latitude")) else float(sample.get("latitude")),
                "longitude": None if pd.isna(sample.get("longitude")) else float(sample.get("longitude")),
                "fuels_in_month_state": sorted(group["fuel"].astype(str).unique().tolist()),
                "eligible_fuels_in_month": sorted(group.loc[group["eligible_publication"], "fuel"].astype(str).unique().tolist()),
            })
        print("WARNING: geography registry is missing current Corsica station(s):")
        print(json.dumps(missing_geography, ensure_ascii=False, indent=2))
        month_state = month_state[~missing_mask].copy()

    days_total = int((end - start).days + 1)
    rows = []
    for epci_siren, epci_group in geo.groupby("epci_siren", sort=True):
        epci_nom = str(epci_group.iloc[0]["epci_nom"])
        registry_ids = set(epci_group["station_id"].astype(str))
        for fuel in FUELS:
            known_ids = sorted(sid for sid in registry_ids if (sid, fuel) in fuel_stations)
            state = month_state[(month_state["epci_siren"] == epci_siren) & (month_state["fuel"] == fuel)].copy()
            eligible = state[state["eligible_publication"]].copy()
            contributing_ids = sorted(eligible["station_id"].astype(str).unique())
            retained_days = int(len(eligible))
            possible_days = len(known_ids) * days_total
            contributor_possible = len(contributing_ids) * days_total
            rows.append({
                "epci_siren": str(epci_siren),
                "epci_nom": epci_nom,
                "fuel": fuel,
                "registry_stations": int(len(registry_ids)),
                "known_fuel_stations": int(len(known_ids)),
                "known_fuel_station_ids": known_ids,
                "contributing_stations": int(len(contributing_ids)),
                "contributing_station_ids": contributing_ids,
                "station_coverage_ratio": None if not known_ids else round(len(contributing_ids) / len(known_ids), 4),
                "retained_station_days": retained_days,
                "possible_station_days_known_fuel": possible_days,
                "effective_coverage_ratio": None if not possible_days else round(retained_days / possible_days, 4),
                "contributor_temporal_coverage_ratio": None if not contributor_possible else round(retained_days / contributor_possible, 4),
                "days_with_any_price": int(eligible["date"].nunique()),
            })

    output = {
        "meta": {
            "schema": "a4c-monthly-territorial-coverage-audit-v1",
            "month": args.month,
            "period_start": start.strftime("%Y-%m-%d"),
            "period_end": end.strftime("%Y-%m-%d"),
            "c1_release_tag": release_tag,
            "c2_reference_daily_target_end": c2_meta.get("daily_target_end"),
            "c2_engine": "A4C-V2-2026-07-23",
            "source_max_date": str(source.get("shared_source_max_date")),
            "definition": "known_fuel_stations = geography-registry stations with at least one declaration of that fuel on or before month end; effective coverage = retained C2 V2 station-days / (known fuel stations × calendar days)",
            "warning": "Diagnostic only. These wider-coverage metrics do not yet change rankability thresholds.",
            "engine_r2_unavailable": engine.get("r2_unavailable"),
            "missing_geography": missing_geography,
        },
        "epci": rows,
    }
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Audit de couverture territoriale — {args.month}",
        "",
        "Diagnostic uniquement : aucun seuil de classement n'est modifié.",
    ]
    if missing_geography:
        lines += ["", "## Stations à rattacher au registre géographique", ""]
        for item in missing_geography:
            lines.append(f"- {item['station_id']} — {item['city']} — {item['address']} — CP {item['cp']}")
    lines += [
        "",
        "| EPCI | Carburant | Stations connues | Stations contributrices | Couverture stations | Couverture effective | Couverture temporelle contributrices |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(rows, key=lambda x: (x["fuel"], x["epci_nom"])):
        sr = "—" if r["station_coverage_ratio"] is None else f"{100*r['station_coverage_ratio']:.1f} %"
        er = "—" if r["effective_coverage_ratio"] is None else f"{100*r['effective_coverage_ratio']:.1f} %"
        tr = "—" if r["contributor_temporal_coverage_ratio"] is None else f"{100*r['contributor_temporal_coverage_ratio']:.1f} %"
        lines.append(f"| {r['epci_nom']} | {r['fuel']} | {r['known_fuel_stations']} | {r['contributing_stations']} | {sr} | {er} | {tr} |")
    markdown = "\n".join(lines) + "\n"
    if args.markdown:
        md_path = ROOT / args.markdown
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
