#!/usr/bin/env python3
"""Real-data V2 eligibility dry-run for carburantscorse2.

This script never writes data.json and never promotes a candidate. It consumes one
isolated C1 prep release, rebuilds the station/day state from the same official rows,
then calls reliability_policy_v2.evaluate() and r2_guard_v2.stale_price_admissible()
on real observations. The output compares the current publication eligibility with a
prospective switch and with a 2026 retroactive simulation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import urllib.request

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap
from a4c_common.shared_release import (
    download_shared_rotterdam_assets,
    load_shared_observations,
)
from carburantscorse2 import r2_guard_v2, reliability_policy_v2, shield_phase_v2
from carburantscorse2.publication import (
    build_gap_series,
    build_publication_state,
    load_bdr_categories,
)
from scripts.resolve_new_bdr_station_brands import (
    DEFAULT_REGISTRY as BDR_REGISTRY,
    fetch_brand,
    load_registry,
    resolved_categories,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs" / "v2"
CORSE_REGISTRY = ROOT / "outputs" / "c1" / "corse_station_brands.json"
C1_META = ROOT / "outputs" / "ufip" / "c1_shared_meta.json"
C1_TAG_FILE = ROOT / "outputs" / "c1" / "shared_release_tag.txt"
LEGACY_BDR = ROOT / "config" / "bdr_categories_published_2026-06-06.csv"
ROTTERDAM_OBSERVED = ROOT / "outputs" / "ufip" / "rotterdam_gazole_observed.csv"
MAIN_DATA_URL = "https://raw.githubusercontent.com/FredericP555/carburantscorse2/main/data.json"
PRINCIPAL_FUELS = {"Gazole", "SP95"}
ALL_FUELS = ("Gazole", "SP95", "E10")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag-prefix", default=os.environ.get("A4C_C1_TAG_PREFIX", "a4c-prep-v2-"))
    parser.add_argument("--release-tag", default=None)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--output", default="outputs/v2/v2-dry-run.json")
    parser.add_argument("--bdr-brand-workers", type=int, default=8)
    parser.add_argument("--bdr-brand-timeout", type=int, default=12)
    return parser.parse_args()


def _as_datetime(value) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).to_pydatetime()


def _as_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _norm_brand(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _is_total_brand(value: str | None) -> bool:
    normalized = _norm_brand(value)
    return normalized == "total" or normalized.startswith("totalenergies") or normalized.startswith("totalaccess")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _merged_bdr_categories() -> dict[str, str]:
    categories = load_bdr_categories(LEGACY_BDR)
    incremental = resolved_categories(load_registry(BDR_REGISTRY))
    for station_id, category in incremental.items():
        categories.setdefault(str(station_id), category)
    return categories


def _load_main_switch_date(fallback: date) -> tuple[date, dict]:
    try:
        request = urllib.request.Request(MAIN_DATA_URL, headers={"User-Agent": "A4C-v2-dry-run/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = (payload.get("meta") or {}).get("daily_target_end")
        if raw:
            last = date.fromisoformat(str(raw))
            return last + timedelta(days=1), {
                "source": "main-data.json",
                "last_published_day": last.isoformat(),
            }
    except Exception as exc:
        return fallback, {"source": "fallback", "error": f"{type(exc).__name__}: {exc}"}
    return fallback, {"source": "fallback", "error": "main daily_target_end absent"}


def _candidate_bdr_brand_ids(state: pd.DataFrame, bouclier: dict, start_day: date, end_day: date) -> set[str]:
    candidates: set[str] = set()
    subset = state[
        (state["department"].astype(str) == "13")
        & state["fuel"].isin(PRINCIPAL_FUELS)
        & (state["date"] >= pd.Timestamp(start_day))
        & (state["date"] <= pd.Timestamp(end_day))
    ]
    for row in subset.itertuples(index=False):
        last_declared = _as_datetime(getattr(row, "source_timestamp", None))
        if last_declared is None:
            continue
        day = pd.Timestamp(row.date).date()
        age = (day - last_declared.date()).days
        if age < reliability_policy_v2.NORMAL_MAX_AGE_DAYS:
            continue
        phase = shield_phase_v2.phase_for_day(bouclier, str(row.fuel), day)
        if phase is None or not at_cap(_as_float(row.price), phase.cap):
            continue
        candidates.add(str(row.station_id))
    return candidates


def _resolve_bdr_brands(station_ids: set[str], workers: int, timeout: int) -> tuple[dict[str, str | None], dict[str, str]]:
    registry = load_registry(BDR_REGISTRY)
    existing = registry.get("stations") or {}
    brands: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    missing: list[str] = []
    for station_id in sorted(station_ids):
        entry = existing.get(station_id)
        brand = str((entry or {}).get("enseigne") or "").strip() if isinstance(entry, dict) else ""
        if brand:
            brands[station_id] = brand
        else:
            missing.append(station_id)
    if not missing:
        return brands, errors

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_to_id = {
            pool.submit(fetch_brand, station_id, timeout=timeout): station_id
            for station_id in missing
        }
        for future in as_completed(future_to_id):
            station_id = future_to_id[future]
            try:
                brand, error = future.result()
            except Exception as exc:
                brand, error = None, f"{type(exc).__name__}: {exc}"
            brands[station_id] = brand
            if error:
                errors[station_id] = str(error)
    return brands, errors


def _series(state: pd.DataFrame, eligibility_column: str) -> dict[str, list[dict]]:
    working = state.copy()
    working["eligible_publication"] = working[eligibility_column].fillna(False).astype(bool)
    cases = [
        ("gazole_sp95", "Gazole", "Gazole"),
        ("sp95_sp95", "SP95", "SP95"),
        ("sp95_e10", "SP95", "E10"),
    ]
    result: dict[str, list[dict]] = {}
    for key, corsica_fuel, bdr_fuel in cases:
        for scope in ("all", "network"):
            for granularity in ("daily", "weekly"):
                result[f"{key}/{granularity}/{scope}"] = build_gap_series(
                    working,
                    corsica_fuel=corsica_fuel,
                    bdr_fuel=bdr_fuel,
                    bdr_scope=scope,
                    granularity=granularity,
                )
    return result


def _compare_series(current: list[dict], candidate: list[dict]) -> dict:
    left = {row["date"]: float(row["ecart"]) for row in current}
    right = {row["date"]: float(row["ecart"]) for row in candidate}
    common = sorted(set(left) & set(right))
    changes = []
    for day in common:
        delta = round(right[day] - left[day], 2)
        if delta != 0:
            changes.append({
                "date": day,
                "actuel": left[day],
                "v2": right[day],
                "delta_c_l": delta,
            })
    changes.sort(key=lambda item: (abs(item["delta_c_l"]), item["date"]), reverse=True)
    abs_values = [abs(item["delta_c_l"]) for item in changes]
    return {
        "common_periods": len(common),
        "changed_periods": len(changes),
        "max_abs_delta_c_l": max(abs_values) if abs_values else 0.0,
        "median_abs_delta_c_l": round(float(pd.Series(abs_values).median()), 2) if abs_values else 0.0,
        "largest_changes": changes[:10],
    }


def main() -> None:
    args = parse_args()
    start_day = date.fromisoformat(args.start)

    fetch_summary = download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix=args.tag_prefix,
        release_tag=args.release_tag,
        registry_output=CORSE_REGISTRY,
        tag_output=C1_TAG_FILE,
    )
    selected_tag = C1_TAG_FILE.read_text(encoding="utf-8").strip()
    c1_meta = _load_json(C1_META)
    available_years = sorted(int(y) for y in c1_meta.get("years", []))
    if not available_years:
        raise RuntimeError("C1 prep bundle declares no source years")

    requested_years = [year for year in available_years if year >= start_day.year - 1]
    observations, source = load_shared_observations(
        requested_years,
        tag_prefix=args.tag_prefix,
        release_tag=selected_tag,
    )
    source_max = date.fromisoformat(str(source.get("shared_source_max_date")))
    end_day = date.fromisoformat(args.end) if args.end else source_max
    if end_day > source_max:
        end_day = source_max
    if end_day < start_day:
        raise RuntimeError("Dry-run end precedes start")

    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("C1 prep bundle has no shield metadata")

    categories = _merged_bdr_categories()
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(end_day),
        bdr_categories=categories,
    )
    if state.empty:
        raise RuntimeError("Real-data publication state is empty")

    corse_payload = _load_json(CORSE_REGISTRY)
    corse_stations = corse_payload.get("stations") or {}
    bdr_brand_ids = _candidate_bdr_brand_ids(state, bouclier, start_day, end_day)
    bdr_brands, bdr_brand_errors = _resolve_bdr_brands(
        bdr_brand_ids,
        args.bdr_brand_workers,
        args.bdr_brand_timeout,
    )

    switch_day, switch_meta = _load_main_switch_date(end_day + timedelta(days=1))

    key_rows = {}
    for row in state.itertuples(index=False):
        day = pd.Timestamp(row.date).date()
        key_rows[(str(row.station_id), day, str(row.fuel))] = row

    current_flags = []
    v2_flags = []
    prospective_flags = []
    reasons = Counter()
    reasons_by_territory = Counter()
    changed_station_days = Counter()
    r2_calls = 0
    r2_true = 0
    r2_false = 0
    r2_unavailable = 0
    r2_errors: Counter[str] = Counter()

    for row in state.itertuples(index=False):
        sid = str(row.station_id)
        day = pd.Timestamp(row.date).date()
        fuel = str(row.fuel)
        current_eligible = bool(row.eligible_publication)
        current_flags.append(current_eligible)

        if day < start_day or day > end_day:
            v2_eligible = current_eligible
            reason = "hors_fenetre_dry_run"
        else:
            last_declared = _as_datetime(getattr(row, "source_timestamp", None))
            activity = {}
            for other_fuel in ALL_FUELS:
                other = key_rows.get((sid, day, other_fuel))
                if other is None:
                    continue
                ts = _as_datetime(getattr(other, "source_timestamp", None))
                if ts is not None:
                    activity[other_fuel] = ts

            phase = shield_phase_v2.phase_for_day(bouclier, fuel, day) if fuel in PRINCIPAL_FUELS else None
            gazole_phase = shield_phase_v2.phase_for_day(bouclier, "Gazole", day)
            sp95_phase = shield_phase_v2.phase_for_day(bouclier, "SP95", day)
            gazole_row = key_rows.get((sid, day, "Gazole"))
            sp95_row = key_rows.get((sid, day, "SP95"))
            gazole_price = _as_float(getattr(gazole_row, "price", None)) if gazole_row else None
            sp95_price = _as_float(getattr(sp95_row, "price", None)) if sp95_row else None
            gazole_cap = gazole_phase.cap if gazole_phase else None
            sp95_cap = sp95_phase.cap if sp95_phase else None

            department = str(row.department)
            if department == "20":
                region_kind = "corsica"
                station_class = classify_registry_entry(corse_stations.get(sid))
                is_total = station_class == TOTAL
                territory_for_r2 = "corsica"
            else:
                region_kind = "mainland"
                is_total = _is_total_brand(bdr_brands.get(sid))
                territory_for_r2 = "bdr"

            r2_verdict = None
            age = reliability_policy_v2.age_days(last_declared, day)
            both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
            if age is not None and age >= reliability_policy_v2.NORMAL_MAX_AGE_DAYS and both_capped:
                r2_calls += 1
                try:
                    r2_verdict = r2_guard_v2.stale_price_admissible(
                        last_declared,
                        day,
                        territory_for_r2,
                        bouclier_metadata=bouclier,
                    )
                    if r2_verdict:
                        r2_true += 1
                    else:
                        r2_false += 1
                except Exception as exc:
                    r2_unavailable += 1
                    r2_errors[f"{type(exc).__name__}: {exc}"] += 1
                    r2_verdict = None

            price_aberrant = getattr(row, "price_aberrant", True)
            latest_price_valid = False if pd.isna(price_aberrant) else not bool(price_aberrant)
            decision = reliability_policy_v2.evaluate(
                day=day,
                region_kind=region_kind,
                target_fuel=fuel,
                last_declared_at=last_declared,
                last_price=_as_float(row.price),
                latest_price_valid=latest_price_valid,
                target_rupture_active=False,
                independently_inactive=False,
                is_total=is_total,
                shield_effective=phase is not None,
                applicable_cap=phase.cap if phase else None,
                phase_started_on=phase.started_on if phase else None,
                activity_by_fuel=activity,
                gazole_price=gazole_price,
                gazole_cap=gazole_cap,
                sp95_price=sp95_price,
                sp95_cap=sp95_cap,
                rotterdam_stale_price_admissible=r2_verdict,
            )
            v2_eligible = bool(decision.eligible)
            reason = decision.reason
            reasons[reason] += 1
            territory_label = "Corse" if department == "20" else "BdR"
            reasons_by_territory[f"{territory_label}/{fuel}/{reason}"] += 1
            if v2_eligible != current_eligible:
                changed_station_days[f"{territory_label}/{fuel}/{current_eligible}->{v2_eligible}"] += 1

        v2_flags.append(v2_eligible)
        prospective_flags.append(current_eligible if day < switch_day else v2_eligible)

    state = state.copy()
    state["eligible_current"] = current_flags
    state["eligible_v2_retroactive"] = v2_flags
    state["eligible_v2_prospective"] = prospective_flags

    series_current = _series(state, "eligible_current")
    series_retro = _series(state, "eligible_v2_retroactive")
    series_prospective = _series(state, "eligible_v2_prospective")

    comparison_retro = {
        key: _compare_series(series_current[key], series_retro[key])
        for key in sorted(series_current)
    }
    comparison_prospective = {
        key: _compare_series(series_current[key], series_prospective[key])
        for key in sorted(series_current)
    }

    observed = pd.read_csv(ROTTERDAM_OBSERVED)
    last_observed = None
    if not observed.empty and "date" in observed.columns:
        last_observed = str(pd.to_datetime(observed["date"]).max().date())

    output = {
        "status": "dry-run-only",
        "production_modified": False,
        "c1_release": {
            "tag_prefix": args.tag_prefix,
            "selected_tag": selected_tag,
            "source_max_date": source_max.isoformat(),
            "rotterdam_last_observed_date": last_observed,
            "fetch": fetch_summary,
        },
        "window": {
            "retroactive_start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "prospective_switch_date": switch_day.isoformat(),
            "prospective_switch_source": switch_meta,
        },
        "engine_calls": {
            "evaluate_station_days": sum(reasons.values()),
            "r2_calls": r2_calls,
            "r2_true": r2_true,
            "r2_false": r2_false,
            "r2_unavailable": r2_unavailable,
            "r2_errors": dict(r2_errors.most_common(20)),
        },
        "eligibility": {
            "reason_counts": dict(reasons.most_common()),
            "reason_counts_by_territory_fuel": dict(reasons_by_territory.most_common()),
            "changed_station_days": dict(changed_station_days.most_common()),
        },
        "bdr_identity_probe": {
            "candidate_station_ids": len(bdr_brand_ids),
            "resolved_brand_count": sum(1 for value in bdr_brands.values() if value),
            "total_brand_count": sum(1 for value in bdr_brands.values() if _is_total_brand(value)),
            "unresolved": bdr_brand_errors,
        },
        "comparison": {
            "NOUVELLE_REGLE_RETROACTIVE_vs_ACTUEL": comparison_retro,
            "NOUVELLE_REGLE_PROSPECTIVE_vs_ACTUEL": comparison_prospective,
        },
        "known_reserves": [
            "rupture events are not present in the current shared price-only snapshot",
            "independent closure/inactivity evidence is not present in the current shared price-only snapshot",
            "BDR Total identity is probed only for stale at-cap candidates and fails closed when unresolved",
            "retrospective window is limited by the years carried in the isolated C1 prep bundle",
        ],
    }

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
