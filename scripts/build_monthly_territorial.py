#!/usr/bin/env python3
"""Build the A4C monthly territorial dataset with the current C2 V2 engine.

The territorial aggregation is new, but the source selection and station-day eligibility are
not reimplemented here: this script deliberately reuses the same C1 pinned release, C2
publication state, BDR perimeter resolver, event guards, shield metadata and V2 reliability
evaluator used by ``scripts/build_v2_production_candidate.py``.

The monthly output is standalone and does not modify ``data.json`` or the public dashboard.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date
import json
import os
from pathlib import Path

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_publication_state, load_bdr_categories
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
MIN_RANK_STATIONS = 3
MIN_RANK_DAY_RATIO = 0.80
MIN_RANK_COVERAGE = 0.80
MIN_C2_CORSE_STATIONS = 5
MIN_C2_BDR_STATIONS = 10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True, help="Complete month to build, YYYY-MM")
    p.add_argument("--geography", default="config/corse_station_geography_2026.csv")
    p.add_argument("--output", help="Output JSON path")
    p.add_argument(
        "--c2-data",
        default="data.json",
        help="C2 production data.json used only to pin the exact C1 release already consumed by C2",
    )
    p.add_argument(
        "--release-tag",
        help="Explicit validated C1 V2 release tag; if omitted it is read from --c2-data",
    )
    p.add_argument("--tag-prefix", default="a4c-v2-shared-")
    return p.parse_args()


def month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    try:
        year, mon = (int(v) for v in month.split("-"))
        last = calendar.monthrange(year, mon)[1]
    except Exception as exc:
        raise SystemExit("--month must be formatted YYYY-MM") from exc
    return pd.Timestamp(year=year, month=mon, day=1), pd.Timestamp(year=year, month=mon, day=last)


def previous_month_bounds(start: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    previous_end = start - pd.Timedelta(1, unit="D")
    return previous_end.replace(day=1).normalize(), previous_end.normalize()


def safe_round(value, digits: int = 4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def load_geography(path: Path) -> pd.DataFrame:
    geo = pd.read_csv(path, dtype=str).fillna("")
    required = {
        "station_id", "localite", "commune", "epci_siren", "epci_nom",
        "source_epci", "date_verification",
    }
    missing = required.difference(geo.columns)
    if missing:
        raise RuntimeError(f"Geography file missing columns: {sorted(missing)}")
    if geo["station_id"].duplicated().any():
        dupes = sorted(geo.loc[geo["station_id"].duplicated(keep=False), "station_id"].unique())
        raise RuntimeError(f"Duplicate station_id in geography file: {dupes[:10]}")
    if (geo["epci_siren"].str.strip() == "").any() or (geo["epci_nom"].str.strip() == "").any():
        raise RuntimeError("Every geography row must have epci_siren and epci_nom")
    return geo


def load_c2_reference(path: Path, month_end: pd.Timestamp) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = dict(payload.get("meta") or {})
    tag = ((meta.get("v2") or {}).get("c1_release_tag") or meta.get("official_shared_release_tag"))
    if not tag:
        raise RuntimeError("C2 reference has no pinned C1 V2 release tag")
    through = meta.get("daily_target_end") or meta.get("official_shared_source_max_date")
    if through and pd.Timestamp(through).normalize() < month_end:
        raise RuntimeError(
            f"C2 reference is not complete through requested month: {through} < {month_end.date()}"
        )
    return meta, str(tag)


def monthly_slice(state: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return state[
        state["eligible_publication"]
        & (state["date"] >= start)
        & (state["date"] <= end)
    ].copy()


def attach_geography(df: pd.DataFrame, geo: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(
        geo[["station_id", "localite", "commune", "epci_siren", "epci_nom"]],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
    missing = sorted(out.loc[out["epci_siren"].isna(), "station_id"].astype(str).unique())
    if missing:
        raise RuntimeError(f"Eligible Corsica station(s) absent from geography registry: {missing}")
    return out


def territory_stats(
    df: pd.DataFrame,
    *,
    days_in_month: int,
    corse_mean: float | None,
    previous_mean_by_epci: dict[tuple[str, str], float],
) -> list[dict]:
    rows: list[dict] = []
    for (epci_siren, epci_nom, fuel), group in df.groupby(
        ["epci_siren", "epci_nom", "fuel"], sort=True
    ):
        station_means = group.groupby("station_id")["price"].mean()
        n_stations = int(group["station_id"].nunique())
        n_station_days = int(len(group))
        n_days_covered = int(group["date"].nunique())
        coverage_ratio = n_station_days / (n_stations * days_in_month) if n_stations else 0.0
        rankable = (
            n_stations >= MIN_RANK_STATIONS
            and n_days_covered >= int(days_in_month * MIN_RANK_DAY_RATIO + 0.999999)
            and coverage_ratio >= MIN_RANK_COVERAGE
        )
        mean_price = float(group["price"].mean())
        previous_mean = previous_mean_by_epci.get((str(epci_siren), str(fuel)))
        communes = sorted(v for v in group["commune"].dropna().astype(str).unique() if v)
        localites = sorted(v for v in group["localite"].dropna().astype(str).unique() if v)
        station_min = float(station_means.min())
        station_max = float(station_means.max())
        rows.append({
            "epci_siren": str(epci_siren),
            "epci_nom": str(epci_nom),
            "fuel": str(fuel),
            "mean_eur_l": safe_round(mean_price, 4),
            "median_station_eur_l": safe_round(station_means.median(), 4),
            "station_mean_min_eur_l": safe_round(station_min, 4),
            "station_mean_max_eur_l": safe_round(station_max, 4),
            "station_mean_spread_cpl": safe_round((station_max - station_min) * 100.0, 2),
            "change_vs_previous_month_cpl": None if previous_mean is None else safe_round((mean_price - previous_mean) * 100.0, 2),
            "vs_corse_cpl": None if corse_mean is None else safe_round((mean_price - corse_mean) * 100.0, 2),
            "n_stations": n_stations,
            "n_station_days": n_station_days,
            "n_days_covered": n_days_covered,
            "coverage_ratio": safe_round(coverage_ratio, 4),
            "n_communes": len(communes),
            "communes": communes,
            "localites": localites,
            "rankable": bool(rankable),
            "sample_note": None if rankable else "échantillon limité — hors classement inter-EPCI",
        })
    return rows


def locality_stats(df: pd.DataFrame, *, days_in_month: int) -> list[dict]:
    rows: list[dict] = []
    for (epci_siren, epci_nom, localite, commune, fuel), group in df.groupby(
        ["epci_siren", "epci_nom", "localite", "commune", "fuel"], sort=True
    ):
        station_means = group.groupby("station_id")["price"].mean()
        n_stations = int(group["station_id"].nunique())
        station_min = float(station_means.min())
        station_max = float(station_means.max())
        rows.append({
            "epci_siren": str(epci_siren),
            "epci_nom": str(epci_nom),
            "localite": str(localite),
            "commune": str(commune),
            "fuel": str(fuel),
            "mean_eur_l": safe_round(group["price"].mean(), 4),
            "median_station_eur_l": safe_round(station_means.median(), 4),
            "station_mean_min_eur_l": safe_round(station_min, 4),
            "station_mean_max_eur_l": safe_round(station_max, 4),
            "station_mean_spread_cpl": safe_round((station_max - station_min) * 100.0, 2),
            "n_stations": n_stations,
            "n_station_days": int(len(group)),
            "n_days_covered": int(group["date"].nunique()),
            "coverage_ratio": safe_round(len(group) / (n_stations * days_in_month), 4) if n_stations else 0.0,
        })
    return rows


def overall_fuel_stats(current_corse: pd.DataFrame, previous_corse: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fuel in FUELS:
        cur = current_corse[current_corse["fuel"] == fuel]
        prev = previous_corse[previous_corse["fuel"] == fuel]
        if cur.empty:
            continue
        mean_ttc = float(cur["price"].mean())
        mean_ht = float(cur["price_ht"].mean())
        prev_ttc = None if prev.empty else float(prev["price"].mean())
        prev_ht = None if prev.empty else float(prev["price_ht"].mean())
        out[fuel] = {
            "mean_ttc_eur_l": safe_round(mean_ttc, 4),
            "mean_ht_eur_l": safe_round(mean_ht, 4),
            "change_ttc_vs_previous_month_cpl": None if prev_ttc is None else safe_round((mean_ttc - prev_ttc) * 100.0, 2),
            "change_ht_vs_previous_month_cpl": None if prev_ht is None else safe_round((mean_ht - prev_ht) * 100.0, 2),
            "n_stations": int(cur["station_id"].nunique()),
            "n_station_days": int(len(cur)),
        }
    return out


def _valid_c2_days(state: pd.DataFrame, fuel: str, start: pd.Timestamp, end: pd.Timestamp) -> set[pd.Timestamp]:
    reliable = monthly_slice(state, start, end)
    reliable = reliable[reliable["fuel"] == fuel]
    c = reliable[reliable["territory"] == "Corse"].groupby("date")["station_id"].nunique()
    b = reliable[reliable["territory"] == "Bouches-du-Rhone"].groupby("date")["station_id"].nunique()
    counts = pd.DataFrame({"c": c, "b": b}).fillna(0)
    valid = counts[(counts["c"] >= MIN_C2_CORSE_STATIONS) & (counts["b"] >= MIN_C2_BDR_STATIONS)].index
    return {pd.Timestamp(v).normalize() for v in valid}


def _scope_month_stats(
    state: pd.DataFrame,
    *,
    fuel: str,
    scope: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict | None:
    valid_days = _valid_c2_days(state, fuel, start, end)
    reliable = monthly_slice(state, start, end)
    reliable = reliable[(reliable["fuel"] == fuel) & reliable["date"].isin(valid_days)]
    corse = reliable[reliable["territory"] == "Corse"]
    bdr_all = reliable[reliable["territory"] == "Bouches-du-Rhone"]
    bdr = bdr_all if scope == "all" else bdr_all[bdr_all["category"] == "network"]
    if corse.empty or bdr.empty:
        return None
    c_ttc = float(corse["price"].mean())
    b_ttc = float(bdr["price"].mean())
    c_ht = float(corse["price_ht"].mean())
    b_ht = float(bdr["price_ht"].mean())
    days_total = int((end - start).days + 1)
    return {
        "corse_ttc_eur_l": safe_round(c_ttc, 4),
        "bdr_ttc_eur_l": safe_round(b_ttc, 4),
        "gap_ttc_cpl": safe_round((c_ttc - b_ttc) * 100.0, 2),
        "corse_ht_eur_l": safe_round(c_ht, 4),
        "bdr_ht_eur_l": safe_round(b_ht, 4),
        "gap_ht_cpl": safe_round((c_ht - b_ht) * 100.0, 2),
        "valid_days": len(valid_days),
        "guard_failed_days": days_total - len(valid_days),
        "n_corse_stations": int(corse["station_id"].nunique()),
        "n_bdr_scope_stations": int(bdr["station_id"].nunique()),
        "n_corse_station_days": int(len(corse)),
        "n_bdr_scope_station_days": int(len(bdr)),
    }


def corsica_bdr_comparison(state: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, prev_start: pd.Timestamp, prev_end: pd.Timestamp) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fuel in FUELS:
        scopes: dict[str, dict] = {}
        for scope in ("all", "network"):
            cur = _scope_month_stats(state, fuel=fuel, scope=scope, start=start, end=end)
            prev = _scope_month_stats(state, fuel=fuel, scope=scope, start=prev_start, end=prev_end)
            if cur is None:
                continue
            if prev is not None:
                cur["gap_ttc_change_vs_previous_month_cpl"] = safe_round(cur["gap_ttc_cpl"] - prev["gap_ttc_cpl"], 2)
                cur["gap_ht_change_vs_previous_month_cpl"] = safe_round(cur["gap_ht_cpl"] - prev["gap_ht_cpl"], 2)
            else:
                cur["gap_ttc_change_vs_previous_month_cpl"] = None
                cur["gap_ht_change_vs_previous_month_cpl"] = None
            scopes[scope] = cur
        out[fuel] = scopes
    return out


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    prev_start, prev_end = previous_month_bounds(start)
    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("The requested month is not complete yet")

    geography_path = ROOT / args.geography
    output_path = ROOT / (args.output or f"outputs/monthly-territories-{args.month}.json")
    c2_path = Path(args.c2_data)
    if not c2_path.is_absolute():
        c2_path = ROOT / c2_path

    geo = load_geography(geography_path)
    c2_meta, c2_release_tag = load_c2_reference(c2_path, end)
    release_tag = args.release_tag or c2_release_tag
    if release_tag != c2_release_tag:
        raise RuntimeError(
            f"Explicit C1 release {release_tag} does not match C2 pinned release {c2_release_tag}"
        )

    # Stage exactly the C1 V2 assets consumed by the current C2 engine, including shield metadata,
    # Corsica station brands, event guards and Rotterdam inputs needed by the V2 stale-price guard.
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
    source_max = pd.Timestamp(source.get("shared_source_max_date")).normalize()
    if source_max < end:
        raise RuntimeError(f"Pinned C1 source incomplete for {args.month}: {source_max.date()} < {end.date()}")
    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy = load_bdr_categories(LEGACY_BDR)
    resolution = _resolve_bdr(observations, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=end,
        bdr_category_resolver=resolver,
    )
    stale_ids = _candidate_stale_bdr_ids(state, bouclier, SWITCH_DAY, end.date())
    resolution["stale_total_candidates"] = _resolve_stale_bdr_candidates(observations, stale_ids, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=end,
        bdr_category_resolver=resolver,
    )

    guards = EventGuards.from_release(release_tag, metadata=c1_meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    # Exact production transition semantics: V2 replaces eligibility from 23 July 2026 onward;
    # earlier comparison days keep the legacy publication state, exactly as C2 production does.
    v2_state, engine_report = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end.date(),
    )

    current = monthly_slice(v2_state, start, end)
    previous = monthly_slice(v2_state, prev_start, prev_end)
    current_corse = attach_geography(current[current["territory"] == "Corse"].copy(), geo)
    previous_corse = attach_geography(previous[previous["territory"] == "Corse"].copy(), geo)

    days_in_month = int((end - start).days + 1)
    previous_epci_means = {
        (str(epci), str(fuel)): float(group["price"].mean())
        for (epci, fuel), group in previous_corse.groupby(["epci_siren", "fuel"])
    }
    epci_rows: list[dict] = []
    for fuel in FUELS:
        fuel_df = current_corse[current_corse["fuel"] == fuel]
        corse_mean = None if fuel_df.empty else float(fuel_df["price"].mean())
        epci_rows.extend(territory_stats(
            fuel_df,
            days_in_month=days_in_month,
            corse_mean=corse_mean,
            previous_mean_by_epci=previous_epci_means,
        ))

    output = {
        "meta": {
            "schema": "a4c-monthly-territories-v2-c2-engine",
            "month": args.month,
            "period_start": start.strftime("%Y-%m-%d"),
            "period_end": end.strftime("%Y-%m-%d"),
            "source_max_date": source_max.strftime("%Y-%m-%d"),
            "c1_release_tag": release_tag,
            "c2_reference_daily_target_end": c2_meta.get("daily_target_end"),
            "c2_engine": "A4C-V2-2026-07-23",
            "c2_v2_switch_date": SWITCH_DAY.isoformat(),
            "c2_main_sha_runtime": os.environ.get("C2_MAIN_SHA"),
            "station_day_eligibility": "scripts.build_v2_production_candidate._evaluate_v2",
            "source_policy": "same pinned C1 V2 release as C2 reference",
            "bdr_perimeters": ["all", "network"],
            "geography_file": str(Path(args.geography)),
            "geography_rows": int(len(geo)),
            "epci_count_registry": int(geo["epci_siren"].nunique()),
            "thresholds": {
                "ranking_min_stations": MIN_RANK_STATIONS,
                "ranking_min_days_ratio": MIN_RANK_DAY_RATIO,
                "ranking_min_coverage_ratio": MIN_RANK_COVERAGE,
                "c2_min_corse_stations_per_day": MIN_C2_CORSE_STATIONS,
                "c2_min_bdr_stations_per_day": MIN_C2_BDR_STATIONS,
            },
            "note": "Prototype indépendant : aucune consommation par le dashboard C2 public ni par WordPress.",
        },
        "corse": overall_fuel_stats(current_corse, previous_corse),
        "corse_vs_bdr": corsica_bdr_comparison(v2_state, start, end, prev_start, prev_end),
        "epci": epci_rows,
        "localities": locality_stats(current_corse, days_in_month=days_in_month),
        "internal_audit": {
            "engine": engine_report,
            "event_guards": guards.audit(),
            "bdr_resolution": resolution,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {output_path} with {len(epci_rows)} EPCI/fuel rows; "
        f"C1={release_tag}; C2 engine=A4C-V2-2026-07-23"
    )


if __name__ == "__main__":
    main()
