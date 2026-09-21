#!/usr/bin/env python3
"""Read-only retrospective dry-run for the TotalEnergies Corsica 45-day shield rule.

This audit compares:
- LEGACY: the exact C2 policy/build logic from main before commit e526ff46,
  where stale Total Corsica prices depended on double-cap / recent-liveness logic;
- CURRENT: the per-fuel Total Corsica rule now on main, where an at-cap price under an
  effective shield is not expired by age alone and UFIP/R2 is the fail-closed continuation guard.

It never writes data.json. Outputs are audit-only CSV/JSON files under outputs/.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap, finite_number
from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2 import r2_guard_v2, reliability_policy_v2, shield_phase_v2
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories
from scripts.build_v2_production_candidate import (
    ALL_FUELS,
    BDR_REGISTRY,
    C1_META,
    C1_TAG,
    CORSE_REGISTRY,
    LEGACY_BDR,
    PRINCIPAL_FUELS,
    ROOT,
    SWITCH_DAY,
    WEEKLY_SWITCH,
    _as_datetime,
    _as_float,
    _bdr_category_resolver,
    _evaluate_v2,
    _is_total_brand,
)
from scripts.resolve_new_bdr_station_brands import _entry_for_day as bdr_entry_for_day
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

LEGACY_MAIN_SHA = "57a6cba12051a055b68eb6fc5bc0615eeab98f7a"
CURRENT_RULE_SHA = "e526ff46cf1229b0d95fd1569260714907d1149e"
FUELS = ("Gazole", "SP95")


@dataclass(frozen=True)
class LegacyDecision:
    eligible: bool
    reason: str
    age_days: int | None


def _legacy_age_days(ts: datetime | None, day: date) -> int | None:
    return None if ts is None else (day - ts.date()).days


def _legacy_normally_fresh(ts: datetime | None, day: date) -> bool:
    age = _legacy_age_days(ts, day)
    return age is not None and 0 <= age < 45


def _legacy_recent_liveness(*, region_kind: str, target_fuel: str,
                            activity_by_fuel: Mapping[str, datetime], day: date) -> bool:
    if region_kind not in {"corsica", "mainland"}:
        raise ValueError("region_kind")
    for fuel, ts in activity_by_fuel.items():
        if fuel == target_fuel:
            continue
        if region_kind == "corsica" and fuel not in {"Gazole", "SP95"}:
            continue
        if _legacy_normally_fresh(ts, day):
            return True
    return False


def _legacy_recent_nonprincipal_liveness(*, activity_by_fuel: Mapping[str, datetime], day: date) -> bool:
    for fuel, ts in activity_by_fuel.items():
        if fuel in {"Gazole", "SP95"}:
            continue
        if _legacy_normally_fresh(ts, day):
            return True
    return False


def _legacy_declaration_eligible_for_phase(last_declared_at: datetime | None,
                                           phase_started_on: date | None) -> bool:
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on >= phase_started_on:
        return True
    age_at_entry = (phase_started_on - declared_on).days
    return 0 <= age_at_entry < 45


def legacy_evaluate(*, day: date, region_kind: str, target_fuel: str,
                    last_declared_at: datetime | None, last_price: float | None,
                    latest_price_valid: bool = True, target_rupture_active: bool = False,
                    independently_inactive: bool = False, is_total: bool = False,
                    shield_effective: bool = False, applicable_cap: float | None = None,
                    phase_started_on: date | None = None,
                    activity_by_fuel: Mapping[str, datetime] | None = None,
                    gazole_price: float | None = None, gazole_cap: float | None = None,
                    sp95_price: float | None = None, sp95_cap: float | None = None,
                    rotterdam_stale_price_admissible: bool | None = None) -> LegacyDecision:
    """Exact legacy reliability policy from C2 main at LEGACY_MAIN_SHA."""
    if region_kind not in {"corsica", "mainland"}:
        raise ValueError("region_kind")
    age = _legacy_age_days(last_declared_at, day)
    if target_rupture_active:
        return LegacyDecision(False, "rupture_active", age)
    if independently_inactive:
        return LegacyDecision(False, "inactive_independant", age)
    if last_declared_at is None or age is None or age < 0 or not latest_price_valid or not finite_number(last_price):
        return LegacyDecision(False, "prix_ou_date_absent_invalide", age)
    if _legacy_normally_fresh(last_declared_at, day):
        return LegacyDecision(True, "normal_45j", age)
    if target_fuel not in {"Gazole", "SP95"}:
        return LegacyDecision(False, "exception_carburant_non_principal", age)
    if not (is_total and shield_effective):
        return LegacyDecision(False, "ancien_hors_exception", age)
    if phase_started_on is None or phase_started_on > day:
        return LegacyDecision(False, "phase_plafond_absente_ou_invalide", age)
    if not _legacy_declaration_eligible_for_phase(last_declared_at, phase_started_on):
        return LegacyDecision(False, "pas_de_resurrection_a_entree_plafond", age)
    if not at_cap(last_price, applicable_cap):
        return LegacyDecision(False, "ancien_pas_au_plafond", age)

    activity_by_fuel = activity_by_fuel or {}
    both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
    if both_capped:
        if region_kind == "corsica":
            if rotterdam_stale_price_admissible is True:
                return LegacyDecision(True, "double_plafond_rotterdam_admissible", age)
            if rotterdam_stale_price_admissible is False:
                return LegacyDecision(False, "double_plafond_rotterdam_verrouille", age)
            return LegacyDecision(False, "double_plafond_rotterdam_indisponible", age)
        if not _legacy_recent_nonprincipal_liveness(activity_by_fuel=activity_by_fuel, day=day):
            return LegacyDecision(False, "double_plafond_bdr_sans_vivacite_autre_carburant", age)
        if rotterdam_stale_price_admissible is True:
            return LegacyDecision(True, "double_plafond_bdr_vivacite_et_rotterdam", age)
        if rotterdam_stale_price_admissible is False:
            return LegacyDecision(False, "double_plafond_rotterdam_verrouille", age)
        return LegacyDecision(False, "double_plafond_rotterdam_indisponible", age)
    if _legacy_recent_liveness(
        region_kind=region_kind,
        target_fuel=target_fuel,
        activity_by_fuel=activity_by_fuel,
        day=day,
    ):
        return LegacyDecision(True, "bouclier_vivacite_45j_renouvelee", age)
    return LegacyDecision(False, "bouclier_sans_vivacite_recente", age)


def evaluate_legacy_state(state: pd.DataFrame, *, bouclier: dict, event_guards,
                          corse_stations: dict, start: date, end: date) -> tuple[pd.DataFrame, dict]:
    """Exact legacy builder evaluation, copied from LEGACY_MAIN_SHA for reproducibility."""
    key_rows = {
        (str(r.station_id), pd.Timestamp(r.date).date(), str(r.fuel)): r
        for r in state.itertuples(index=False)
    }
    bdr_entries = load_registry(BDR_REGISTRY).get("stations") or {}
    reasons = Counter()
    reasons_by_territory = Counter()
    r2_calls = r2_true = r2_false = r2_unavailable = 0
    r2_errors = Counter()
    eligible: list[bool] = []
    phase_cache = {}

    def phase(fuel: str, day: date):
        key = (fuel, day)
        if key not in phase_cache:
            phase_cache[key] = shield_phase_v2.phase_for_day(bouclier, fuel, day)
        return phase_cache[key]

    for row in state.itertuples(index=False):
        day = pd.Timestamp(row.date).date()
        sid = str(row.station_id)
        fuel = str(row.fuel)
        current = bool(row.eligible_publication)
        if day < start or day > end:
            eligible.append(current)
            continue

        last_declared = _as_datetime(getattr(row, "source_timestamp", None))
        activity = {}
        for other_fuel in ALL_FUELS:
            other = key_rows.get((sid, day, other_fuel))
            if other is not None:
                ts = _as_datetime(getattr(other, "source_timestamp", None))
                if ts is not None:
                    activity[other_fuel] = ts

        target_phase = phase(fuel, day) if fuel in PRINCIPAL_FUELS else None
        gp = phase("Gazole", day)
        sp = phase("SP95", day)
        gr = key_rows.get((sid, day, "Gazole"))
        sr = key_rows.get((sid, day, "SP95"))
        gazole_price = _as_float(getattr(gr, "price", None)) if gr else None
        sp95_price = _as_float(getattr(sr, "price", None)) if sr else None
        gazole_cap = gp.cap if gp else None
        sp95_cap = sp.cap if sp else None

        department = str(row.department)
        if department == "20":
            region_kind = "corsica"
            territory_r2 = "corsica"
            is_total = classify_registry_entry(corse_stations.get(sid), on_date=day) == TOTAL
            territory_label = "Corse"
        else:
            region_kind = "mainland"
            territory_r2 = "bdr"
            raw_entry = bdr_entries.get(sid) if isinstance(bdr_entries, dict) else None
            entry = bdr_entry_for_day(raw_entry, day)
            is_total = _is_total_brand((entry or {}).get("enseigne") if isinstance(entry, dict) else None)
            territory_label = "BdR"

        r2_verdict = None
        age = _legacy_age_days(last_declared, day)
        both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)
        if fuel in PRINCIPAL_FUELS and age is not None and age >= 45 and both_capped:
            r2_calls += 1
            try:
                r2_verdict = r2_guard_v2.stale_price_admissible(
                    last_declared,
                    day,
                    territory_r2,
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
        decision = legacy_evaluate(
            day=day,
            region_kind=region_kind,
            target_fuel=fuel,
            last_declared_at=last_declared,
            last_price=_as_float(row.price),
            latest_price_valid=latest_price_valid,
            target_rupture_active=event_guards.rupture_active(sid, fuel, day),
            independently_inactive=event_guards.independently_inactive(sid, day),
            is_total=is_total,
            shield_effective=target_phase is not None,
            applicable_cap=target_phase.cap if target_phase else None,
            phase_started_on=target_phase.started_on if target_phase else None,
            activity_by_fuel=activity,
            gazole_price=gazole_price,
            gazole_cap=gazole_cap,
            sp95_price=sp95_price,
            sp95_cap=sp95_cap,
            rotterdam_stale_price_admissible=r2_verdict,
        )
        eligible.append(bool(decision.eligible))
        reasons[decision.reason] += 1
        reasons_by_territory[f"{territory_label}/{fuel}/{decision.reason}"] += 1

    out = state.copy()
    out["eligible_publication"] = eligible
    return out, {
        "reason_counts": dict(reasons),
        "reason_counts_by_territory_fuel": dict(reasons_by_territory),
        "r2_calls": r2_calls,
        "r2_true": r2_true,
        "r2_false": r2_false,
        "r2_unavailable": r2_unavailable,
        "r2_errors": dict(r2_errors),
    }


def _published_weekly_map(data: dict, fuel: str, group: str) -> dict[str, float]:
    if fuel == "Gazole":
        rows = data["DATA"]["gazole"]["sp95"]["weekly"][group]
    elif fuel == "SP95":
        rows = data["DATA"]["sp95"]["sp95"]["weekly"][group]
    else:
        raise ValueError(fuel)
    return {str(row["date"]): float(row["ecart"]) for row in rows}


def _weekly_corsica(frame: pd.DataFrame, fuel: str, end: date) -> dict[str, dict]:
    x = frame[
        frame["eligible_publication"]
        & frame["territory"].eq("Corse")
        & frame["fuel"].eq(fuel)
        & (frame["date"] >= pd.Timestamp(WEEKLY_SWITCH))
        & (frame["date"] <= pd.Timestamp(end))
    ].copy()
    x["week"] = x["date"] - pd.to_timedelta(x["date"].dt.weekday, unit="D")
    out = {}
    for week, g in x.groupby("week"):
        week_day = pd.Timestamp(week).date()
        if week_day + timedelta(days=6) > end:
            continue
        out[week_day.isoformat()] = {
            "ht": float(g["price_ht"].mean()),
            "ttc": float(g["price"].mean()),
            "stations": int(g["station_id"].nunique()),
            "station_days": int(len(g)),
        }
    return out


def _daily_corsica(frame: pd.DataFrame, fuel: str, end: date) -> dict[str, dict]:
    x = frame[
        frame["eligible_publication"]
        & frame["territory"].eq("Corse")
        & frame["fuel"].eq(fuel)
        & (frame["date"] >= pd.Timestamp(SWITCH_DAY))
        & (frame["date"] <= pd.Timestamp(end))
    ].copy()
    out = {}
    for day, g in x.groupby("date"):
        key = pd.Timestamp(day).date().isoformat()
        out[key] = {
            "ht": float(g["price_ht"].mean()),
            "ttc": float(g["price"].mean()),
            "stations": int(g["station_id"].nunique()),
            "station_days": int(len(g)),
        }
    return out


def _gap_map(state: pd.DataFrame, fuel: str, scope: str) -> dict[str, float]:
    rows = build_gap_series(
        state,
        corsica_fuel=fuel,
        bdr_fuel=fuel,
        bdr_scope=scope,
        granularity="weekly",
        include_levels=False,
    )
    return {str(row["date"]): float(row["ecart"]) for row in rows}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--release-tag", required=True)
    p.add_argument("--output-dir", default="outputs/retrospective-total-corsica-45d")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    data_path = ROOT / "data.json"
    before_sha = _sha256(data_path)
    baseline = json.loads(data_path.read_text(encoding="utf-8"))
    end = date.fromisoformat(str((baseline.get("meta") or {})["daily_target_end"]))
    if end < SWITCH_DAY:
        raise RuntimeError("Published C2 data predates V2 retrospective window")

    download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix="a4c-v2-shared-",
        release_tag=args.release_tag,
        registry_output=CORSE_REGISTRY,
        tag_output=C1_TAG,
    )
    meta = json.loads(C1_META.read_text(encoding="utf-8"))
    years = sorted(int(y) for y in meta.get("years", []))
    observations, source = load_shared_observations(
        years,
        tag_prefix="a4c-v2-shared-",
        release_tag=args.release_tag,
    )
    source_max = date.fromisoformat(str(source["shared_source_max_date"]))
    if source_max < end:
        raise RuntimeError(f"Pinned C1 release ends {source_max}, before published C2 {end}")

    bouclier = source.get("bouclier") or meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy_bdr = load_bdr_categories(LEGACY_BDR)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy_bdr, registry)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(end),
        bdr_category_resolver=resolver,
    )
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}

    old_guards = EventGuards.from_release(args.release_tag, metadata=meta)
    new_guards = EventGuards.from_release(args.release_tag, metadata=meta)
    old_state, old_engine = evaluate_legacy_state(
        state,
        bouclier=bouclier,
        event_guards=old_guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end,
    )
    new_state, new_engine = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=new_guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end,
    )

    # Guard: the code change is Corsica-only. BDR eligibility must be identical old/new.
    bdr_mask = state["territory"].eq("Bouches-du-Rhone") & (state["date"] >= pd.Timestamp(SWITCH_DAY))
    bdr_diff = (
        old_state.loc[bdr_mask, "eligible_publication"].astype(bool).to_numpy()
        != new_state.loc[bdr_mask, "eligible_publication"].astype(bool).to_numpy()
    )
    if bool(bdr_diff.any()):
        raise RuntimeError(f"Dry-run contamination: {int(bdr_diff.sum())} BDR station-days differ")

    compare = state[[
        "station_id", "territory", "fuel", "date", "price", "price_ht",
        "source_timestamp", "department",
    ]].copy()
    compare["old_eligible"] = old_state["eligible_publication"].astype(bool).to_numpy()
    compare["new_eligible"] = new_state["eligible_publication"].astype(bool).to_numpy()
    compare = compare[
        compare["territory"].eq("Corse")
        & compare["fuel"].isin(FUELS)
        & (compare["date"] >= pd.Timestamp(SWITCH_DAY))
        & (compare["date"] <= pd.Timestamp(end))
    ].copy()
    compare["changed"] = compare["old_eligible"] != compare["new_eligible"]
    compare["direction"] = ""
    compare.loc[~compare["old_eligible"] & compare["new_eligible"], "direction"] = "reintroduced"
    compare.loc[compare["old_eligible"] & ~compare["new_eligible"], "direction"] = "removed"

    changed = compare[compare["changed"]].copy()
    changed["station_id"] = changed["station_id"].astype(str)
    changed["date"] = pd.to_datetime(changed["date"]).dt.strftime("%Y-%m-%d")
    changed["source_timestamp"] = pd.to_datetime(changed["source_timestamp"]).astype(str)
    changed["age_days"] = (
        pd.to_datetime(changed["date"]) - pd.to_datetime(changed["source_timestamp"]).dt.normalize()
    ).dt.days

    # Every changed station-day must be Total on that historical day and at the relevant cap.
    violations = []
    for r in changed.itertuples(index=False):
        day = date.fromisoformat(str(r.date))
        sid = str(r.station_id)
        is_total = classify_registry_entry(corse_stations.get(sid), on_date=day) == TOTAL
        phase = shield_phase_v2.phase_for_day(bouclier, str(r.fuel), day)
        if not is_total or phase is None or not at_cap(float(r.price), phase.cap) or int(r.age_days) < 45:
            violations.append((sid, str(r.fuel), str(r.date), is_total, phase.cap if phase else None, r.price, r.age_days))
    if violations:
        raise RuntimeError(f"Changed rows violate intended Total/at-cap/>=45d scope: {violations[:10]}")

    old_daily = {fuel: _daily_corsica(old_state, fuel, end) for fuel in FUELS}
    new_daily = {fuel: _daily_corsica(new_state, fuel, end) for fuel in FUELS}
    daily_rows = []
    for fuel in FUELS:
        days = sorted(set(old_daily[fuel]) | set(new_daily[fuel]))
        for day in days:
            o = old_daily[fuel].get(day)
            n = new_daily[fuel].get(day)
            if not o or not n:
                continue
            c = changed[(changed["fuel"] == fuel) & (changed["date"] == day)]
            daily_rows.append({
                "date": day,
                "fuel": fuel,
                "old_stations": o["stations"],
                "new_stations": n["stations"],
                "station_count_delta": n["stations"] - o["stations"],
                "reintroduced_station_days": int((c["direction"] == "reintroduced").sum()),
                "removed_station_days": int((c["direction"] == "removed").sum()),
                "old_mean_ttc_eur_l": round(o["ttc"], 6),
                "new_mean_ttc_eur_l": round(n["ttc"], 6),
                "delta_ttc_c_l": round((n["ttc"] - o["ttc"]) * 100.0, 4),
                "old_mean_ht_eur_l": round(o["ht"], 6),
                "new_mean_ht_eur_l": round(n["ht"], 6),
                "delta_ht_c_l": round((n["ht"] - o["ht"]) * 100.0, 4),
            })

    old_weekly = {fuel: _weekly_corsica(old_state, fuel, end) for fuel in FUELS}
    new_weekly = {fuel: _weekly_corsica(new_state, fuel, end) for fuel in FUELS}
    old_gap = {
        fuel: {scope: _gap_map(old_state, fuel, scope) for scope in ("all", "network")}
        for fuel in FUELS
    }
    new_gap = {
        fuel: {scope: _gap_map(new_state, fuel, scope) for scope in ("all", "network")}
        for fuel in FUELS
    }
    published = {
        fuel: {
            "all": _published_weekly_map(baseline, fuel, "all"),
            "network": _published_weekly_map(baseline, fuel, "reseau"),
        }
        for fuel in FUELS
    }

    changed_dt = changed.copy()
    changed_dt["date_dt"] = pd.to_datetime(changed_dt["date"])
    changed_dt["week"] = changed_dt["date_dt"] - pd.to_timedelta(changed_dt["date_dt"].dt.weekday, unit="D")

    weekly_rows = []
    for fuel in FUELS:
        weeks = sorted(set(old_weekly[fuel]) | set(new_weekly[fuel]))
        for week in weeks:
            week_day = date.fromisoformat(week)
            if week_day < WEEKLY_SWITCH or week_day + timedelta(days=6) > end:
                continue
            o = old_weekly[fuel].get(week)
            n = new_weekly[fuel].get(week)
            if not o or not n:
                continue
            c = changed_dt[(changed_dt["fuel"] == fuel) & (changed_dt["week"] == pd.Timestamp(week))]
            ids_reintroduced = sorted(c.loc[c["direction"] == "reintroduced", "station_id"].astype(str).unique())
            ids_removed = sorted(c.loc[c["direction"] == "removed", "station_id"].astype(str).unique())
            rule_delta_ht = (n["ht"] - o["ht"]) * 100.0
            row = {
                "week_start": week,
                "week_end": (week_day + timedelta(days=6)).isoformat(),
                "fuel": fuel,
                "old_unique_stations": o["stations"],
                "new_unique_stations": n["stations"],
                "unique_station_delta": n["stations"] - o["stations"],
                "reintroduced_station_days": int((c["direction"] == "reintroduced").sum()),
                "removed_station_days": int((c["direction"] == "removed").sum()),
                "reintroduced_unique_stations": len(ids_reintroduced),
                "removed_unique_stations": len(ids_removed),
                "reintroduced_station_ids": ",".join(ids_reintroduced),
                "removed_station_ids": ",".join(ids_removed),
                "old_mean_ttc_eur_l": round(o["ttc"], 6),
                "new_mean_ttc_eur_l": round(n["ttc"], 6),
                "delta_ttc_c_l": round((n["ttc"] - o["ttc"]) * 100.0, 4),
                "old_mean_ht_eur_l": round(o["ht"], 6),
                "new_mean_ht_eur_l": round(n["ht"], 6),
                "delta_ht_c_l": round(rule_delta_ht, 4),
            }
            for scope in ("all", "network"):
                pub = published[fuel][scope].get(week)
                old_re = old_gap[fuel][scope].get(week)
                new_re = new_gap[fuel][scope].get(week)
                row[f"published_{scope}_gap_ht_c_l"] = pub
                row[f"old_recomputed_{scope}_gap_ht_c_l"] = old_re
                row[f"new_recomputed_{scope}_gap_ht_c_l"] = new_re
                row[f"recomputed_rule_delta_{scope}_gap_c_l"] = (
                    None if old_re is None or new_re is None else round(new_re - old_re, 4)
                )
                row[f"published_plus_rule_delta_{scope}_gap_ht_c_l"] = (
                    None if pub is None else round(pub + rule_delta_ht, 4)
                )
                row[f"old_recomputed_minus_published_{scope}_c_l"] = (
                    None if pub is None or old_re is None else round(old_re - pub, 4)
                )
            weekly_rows.append(row)

    daily_df = pd.DataFrame(daily_rows).sort_values(["date", "fuel"])
    weekly_df = pd.DataFrame(weekly_rows).sort_values(["week_start", "fuel"])
    changed = changed.sort_values(["date", "fuel", "station_id"])

    daily_path = out_dir / "daily.csv"
    weekly_path = out_dir / "weekly.csv"
    changed_path = out_dir / "changed_station_days.csv"
    summary_path = out_dir / "summary.json"
    daily_df.to_csv(daily_path, index=False)
    weekly_df.to_csv(weekly_path, index=False)
    changed.to_csv(changed_path, index=False)

    summary = {
        "schema": "a4c-total-corsica-45d-retrospective-v1",
        "mode": "read-only-dry-run",
        "writes_data_json": False,
        "legacy_main_sha": LEGACY_MAIN_SHA,
        "current_rule_sha": CURRENT_RULE_SHA,
        "release_tag": args.release_tag,
        "source_max_date": source_max.isoformat(),
        "daily_start": SWITCH_DAY.isoformat(),
        "weekly_start": WEEKLY_SWITCH.isoformat(),
        "through": end.isoformat(),
        "data_json_sha256_before": before_sha,
        "changed_station_days": int(len(changed)),
        "reintroduced_station_days": int((changed["direction"] == "reintroduced").sum()),
        "removed_station_days": int((changed["direction"] == "removed").sum()),
        "changed_by_fuel_direction": (
            changed.groupby(["fuel", "direction"]).size().astype(int).to_dict()
            if not changed.empty else {}
        ),
        "unique_changed_station_ids_by_fuel": {
            fuel: sorted(changed.loc[changed["fuel"] == fuel, "station_id"].astype(str).unique().tolist())
            for fuel in FUELS
        },
        "legacy_engine": old_engine,
        "current_engine": new_engine,
        "bdr_eligibility_difference_count": int(bdr_diff.sum()),
        "weekly_rows": weekly_rows,
    }

    # JSON cannot encode tuple keys from pandas groupby directly.
    summary["changed_by_fuel_direction"] = {
        f"{fuel}/{direction}": int(count)
        for (fuel, direction), count in (
            changed.groupby(["fuel", "direction"]).size().items() if not changed.empty else []
        )
    }

    after_sha = _sha256(data_path)
    summary["data_json_sha256_after"] = after_sha
    summary["data_json_unchanged"] = before_sha == after_sha
    if before_sha != after_sha:
        raise RuntimeError("DRY-RUN VIOLATION: data.json changed")

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "retrospective dry-run complete",
        "data_json_unchanged": True,
        "changed_station_days": summary["changed_station_days"],
        "reintroduced_station_days": summary["reintroduced_station_days"],
        "removed_station_days": summary["removed_station_days"],
        "changed_by_fuel_direction": summary["changed_by_fuel_direction"],
        "weekly_rows": weekly_rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
