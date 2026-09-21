#!/usr/bin/env python3
"""Build a one-time, strictly scoped historical correction candidate.

The correction applies ONLY the isolated effect of the 2026-09-21 TotalEnergies Corsica
45-day rule change to already-published SP95 gap series.

Method:
- recompute OLD and NEW eligibility on the same pinned C1 release;
- calculate only the Corsica SP95 HT mean delta (NEW - OLD) by day/week;
- add that isolated delta to the already-published gap, preserving the published BDR side
  and every other historical choice;
- never rewrite Gazole, margins, dates, topology, or any period before the V2 switches.

This script writes a candidate file and audit report. It never writes data.json.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap
from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2 import shield_phase_v2
from carburantscorse2.publication import build_publication_state, load_bdr_categories
from scripts.audit_total_corsica_45d_retrospective import (
    evaluate_legacy_state,
    _daily_corsica,
    _weekly_corsica,
)
from scripts.build_v2_production_candidate import (
    BDR_REGISTRY,
    C1_META,
    C1_TAG,
    CORSE_REGISTRY,
    LEGACY_BDR,
    ROOT,
    SWITCH_DAY,
    WEEKLY_SWITCH,
    _bdr_category_resolver,
    _evaluate_v2,
)
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

EXPECTED_BASELINE_SHA256 = "7fb5b2ff018e78483f4a08fcfe5bb10a791ac844ceaa5ebc6097082b9e72c89b"
EXPECTED_RELEASE_TAG = "a4c-v2-shared-20260921T160119Z-35622254213"
EXPECTED_REINTRODUCED_STATION_DAYS = 663
EXPECTED_UNIQUE_STATIONS = 17
CORRECTION_ID = "total-corsica-sp95-shield-45d-20260921"
TARGET_REFS = ("sp95", "e10")
TARGET_GROUPS = ("all", "reseau")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows_by_date(rows: list[dict]) -> dict[str, dict]:
    return {str(row["date"]): row for row in rows}


def _mean_delta_maps(old_state: pd.DataFrame, new_state: pd.DataFrame, end: date) -> tuple[dict[str, float], dict[str, float]]:
    old_daily = _daily_corsica(old_state, "SP95", end)
    new_daily = _daily_corsica(new_state, "SP95", end)
    old_weekly = _weekly_corsica(old_state, "SP95", end)
    new_weekly = _weekly_corsica(new_state, "SP95", end)

    daily: dict[str, float] = {}
    for day in sorted(set(old_daily) | set(new_daily)):
        if day not in old_daily or day not in new_daily:
            raise RuntimeError(f"SP95 daily period missing from old/new comparison: {day}")
        daily[day] = (new_daily[day]["ht"] - old_daily[day]["ht"]) * 100.0

    weekly: dict[str, float] = {}
    for week in sorted(set(old_weekly) | set(new_weekly)):
        if week not in old_weekly or week not in new_weekly:
            raise RuntimeError(f"SP95 weekly period missing from old/new comparison: {week}")
        weekly[week] = (new_weekly[week]["ht"] - old_weekly[week]["ht"]) * 100.0
    return daily, weekly


def _changed_station_days(base_state: pd.DataFrame, old_state: pd.DataFrame, new_state: pd.DataFrame,
                          corse_stations: dict, bouclier: dict, end: date) -> pd.DataFrame:
    compare = base_state[[
        "station_id", "territory", "fuel", "date", "price", "source_timestamp"
    ]].copy()
    compare["old_eligible"] = old_state["eligible_publication"].astype(bool).to_numpy()
    compare["new_eligible"] = new_state["eligible_publication"].astype(bool).to_numpy()
    changed = compare[
        compare["territory"].eq("Corse")
        & (compare["date"] >= pd.Timestamp(SWITCH_DAY))
        & (compare["date"] <= pd.Timestamp(end))
        & (compare["old_eligible"] != compare["new_eligible"])
    ].copy()

    removed = changed[changed["old_eligible"] & ~changed["new_eligible"]]
    if not removed.empty:
        raise RuntimeError(f"Correction would remove {len(removed)} previously eligible station-days")

    if set(changed["fuel"].astype(str).unique()) - {"SP95"}:
        raise RuntimeError(f"Correction affects non-SP95 fuels: {sorted(changed['fuel'].astype(str).unique())}")

    changed["station_id"] = changed["station_id"].astype(str)
    changed["date_str"] = pd.to_datetime(changed["date"]).dt.strftime("%Y-%m-%d")
    changed["age_days"] = (
        pd.to_datetime(changed["date"]) - pd.to_datetime(changed["source_timestamp"]).dt.normalize()
    ).dt.days

    violations = []
    for row in changed.itertuples(index=False):
        day = pd.Timestamp(row.date).date()
        sid = str(row.station_id)
        phase = shield_phase_v2.phase_for_day(bouclier, "SP95", day)
        is_total = classify_registry_entry(corse_stations.get(sid), on_date=day) == TOTAL
        if (
            not is_total
            or phase is None
            or not at_cap(float(row.price), phase.cap)
            or int(row.age_days) < 45
            or bool(row.old_eligible)
            or not bool(row.new_eligible)
        ):
            violations.append({
                "station_id": sid,
                "date": day.isoformat(),
                "is_total": is_total,
                "phase_cap": None if phase is None else phase.cap,
                "price": row.price,
                "age_days": row.age_days,
                "old_eligible": row.old_eligible,
                "new_eligible": row.new_eligible,
            })
    if violations:
        raise RuntimeError(f"Changed rows escape intended correction scope: {violations[:10]}")

    if len(changed) != EXPECTED_REINTRODUCED_STATION_DAYS:
        raise RuntimeError(
            f"Expected {EXPECTED_REINTRODUCED_STATION_DAYS} reintroduced SP95 station-days, got {len(changed)}"
        )
    unique = sorted(changed["station_id"].unique().tolist())
    if len(unique) != EXPECTED_UNIQUE_STATIONS:
        raise RuntimeError(f"Expected {EXPECTED_UNIQUE_STATIONS} unique stations, got {len(unique)}")
    return changed


def _correct_series(candidate: dict, *, daily_delta: dict[str, float], weekly_delta: dict[str, float],
                    end: date, weekly_end: date) -> tuple[list[dict], list[dict]]:
    daily_changes: list[dict] = []
    weekly_changes: list[dict] = []

    # Strong invariant: Gazole and margins are byte-for-byte/deep-equal to baseline later.
    for ref in TARGET_REFS:
        for group in TARGET_GROUPS:
            rows = candidate["DATA"]["sp95"][ref]["daily"][group]
            for row in rows:
                day = date.fromisoformat(str(row["date"]))
                if day < SWITCH_DAY or day > end:
                    continue
                delta = float(daily_delta.get(day.isoformat(), 0.0))
                old = float(row["ecart"])
                new = round(old + delta, 2)
                if new != old:
                    daily_changes.append({
                        "path": f"DATA/sp95/{ref}/daily/{group}",
                        "date": day.isoformat(),
                        "old_ecart_ht_c_l": old,
                        "delta_corse_ht_c_l": round(delta, 6),
                        "new_ecart_ht_c_l": new,
                    })
                    row["ecart"] = new

            rows = candidate["DATA"]["sp95"][ref]["weekly"][group]
            for row in rows:
                week = date.fromisoformat(str(row["date"]))
                if week < WEEKLY_SWITCH or week + timedelta(days=6) > weekly_end:
                    continue
                delta = float(weekly_delta.get(week.isoformat(), 0.0))
                old = float(row["ecart"])
                new = round(old + delta, 2)
                if new != old:
                    weekly_changes.append({
                        "path": f"DATA/sp95/{ref}/weekly/{group}",
                        "week_start": week.isoformat(),
                        "old_ecart_ht_c_l": old,
                        "delta_corse_ht_c_l": round(delta, 6),
                        "new_ecart_ht_c_l": new,
                    })
                    row["ecart"] = new

    return daily_changes, weekly_changes


def _assert_only_allowed_changes(baseline: dict, candidate: dict) -> None:
    if candidate["DATA"]["gazole"] != baseline["DATA"]["gazole"]:
        raise RuntimeError("Gazole public history changed")
    if candidate["MARGES_GZ"] != baseline["MARGES_GZ"]:
        raise RuntimeError("Gazole margin history changed")

    for ref, grans in baseline["DATA"]["sp95"].items():
        for gran, groups in grans.items():
            for group, old_rows in groups.items():
                new_rows = candidate["DATA"]["sp95"][ref][gran][group]
                if len(new_rows) != len(old_rows):
                    raise RuntimeError(f"Series topology changed: DATA/sp95/{ref}/{gran}/{group}")
                if [r["date"] for r in new_rows] != [r["date"] for r in old_rows]:
                    raise RuntimeError(f"Series dates changed: DATA/sp95/{ref}/{gran}/{group}")
                allowed = ref in TARGET_REFS and group in TARGET_GROUPS and gran in {"daily", "weekly"}
                if not allowed and new_rows != old_rows:
                    raise RuntimeError(f"Unexpected SP95 series changed: DATA/sp95/{ref}/{gran}/{group}")
                if allowed:
                    boundary = SWITCH_DAY if gran == "daily" else WEEKLY_SWITCH
                    for old, new in zip(old_rows, new_rows):
                        day = date.fromisoformat(str(old["date"]))
                        if day < boundary and new != old:
                            raise RuntimeError(
                                f"Protected pre-correction row changed: DATA/sp95/{ref}/{gran}/{group}/{day}"
                            )
                        if day >= boundary:
                            if set(new) != set(old):
                                raise RuntimeError(
                                    f"Row shape changed: DATA/sp95/{ref}/{gran}/{group}/{day}"
                                )
                            for key in old:
                                if key != "ecart" and new.get(key) != old.get(key):
                                    raise RuntimeError(
                                        f"Non-ecart field changed: DATA/sp95/{ref}/{gran}/{group}/{day}/{key}"
                                    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--release-tag", default=EXPECTED_RELEASE_TAG)
    p.add_argument("--output", default="outputs/historical-correction-total-corsica-45d/candidate.json")
    p.add_argument("--report", default="outputs/historical-correction-total-corsica-45d/report.json")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.release_tag != EXPECTED_RELEASE_TAG:
        raise RuntimeError(
            f"One-time correction is pinned to {EXPECTED_RELEASE_TAG}, got {args.release_tag}"
        )

    baseline_path = ROOT / "data.json"
    baseline_sha = _sha256(baseline_path)
    if baseline_sha != EXPECTED_BASELINE_SHA256:
        raise RuntimeError(
            "Historical correction baseline changed; refusing to apply stale correction plan: "
            f"expected {EXPECTED_BASELINE_SHA256}, got {baseline_sha}"
        )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    end = date.fromisoformat(str((baseline.get("meta") or {})["daily_target_end"]))
    weekly_end = date.fromisoformat(str((baseline.get("meta") or {})["weekly_complete_through"]))

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
        raise RuntimeError(f"Pinned source {source_max} is older than published target {end}")
    bouclier = source.get("bouclier") or meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy_bdr = load_bdr_categories(LEGACY_BDR)
    registry = load_registry(BDR_REGISTRY)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(end),
        bdr_category_resolver=_bdr_category_resolver(legacy_bdr, registry),
    )
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}

    old_state, old_engine = evaluate_legacy_state(
        state,
        bouclier=bouclier,
        event_guards=EventGuards.from_release(args.release_tag, metadata=meta),
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end,
    )
    new_state, new_engine = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=EventGuards.from_release(args.release_tag, metadata=meta),
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=end,
    )

    bdr_mask = state["territory"].eq("Bouches-du-Rhone") & (state["date"] >= pd.Timestamp(SWITCH_DAY))
    bdr_diff = (
        old_state.loc[bdr_mask, "eligible_publication"].astype(bool).to_numpy()
        != new_state.loc[bdr_mask, "eligible_publication"].astype(bool).to_numpy()
    )
    if bool(bdr_diff.any()):
        raise RuntimeError(f"BDR contamination detected: {int(bdr_diff.sum())} station-days")

    changed = _changed_station_days(state, old_state, new_state, corse_stations, bouclier, end)
    daily_delta, weekly_delta = _mean_delta_maps(old_state, new_state, end)

    candidate = deepcopy(baseline)
    daily_changes, weekly_changes = _correct_series(
        candidate,
        daily_delta=daily_delta,
        weekly_delta=weekly_delta,
        end=end,
        weekly_end=weekly_end,
    )

    correction = {
        "id": CORRECTION_ID,
        "applied_on": "2026-09-21",
        "reason": (
            "TotalEnergies Corsica SP95 prices at the active shield cap must not expire solely "
            "because the last declaration is at least 45 days old; per-fuel UFIP/R2 controls continuation."
        ),
        "method": (
            "Published gap plus isolated NEW-minus-LEGACY Corsica SP95 HT mean delta; "
            "published BDR side and all unrelated history preserved."
        ),
        "source_release_tag": args.release_tag,
        "daily_window": [SWITCH_DAY.isoformat(), end.isoformat()],
        "weekly_window": [WEEKLY_SWITCH.isoformat(), weekly_end.isoformat()],
        "reintroduced_station_days": int(len(changed)),
        "unique_station_ids": sorted(changed["station_id"].astype(str).unique().tolist()),
        "bdr_eligibility_difference_count": int(bdr_diff.sum()),
        "gazole_history_changed": False,
        "margins_changed": False,
        "daily_rows_changed": len(daily_changes),
        "weekly_rows_changed": len(weekly_changes),
    }
    v2 = candidate.setdefault("meta", {}).setdefault("v2", {})
    corrections = list(v2.get("historical_corrections") or [])
    if any(item.get("id") == CORRECTION_ID for item in corrections if isinstance(item, dict)):
        raise RuntimeError(f"Correction {CORRECTION_ID} already present")
    corrections.append(correction)
    v2["historical_corrections"] = corrections

    _assert_only_allowed_changes(baseline, candidate)

    output = ROOT / args.output
    report_path = ROOT / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "schema": "a4c-total-corsica-45d-historical-correction-v1",
        "status": "candidate-only",
        "writes_data_json": False,
        "baseline_sha256": baseline_sha,
        "candidate_sha256": _sha256(output),
        "release_tag": args.release_tag,
        "through": end.isoformat(),
        "weekly_through": weekly_end.isoformat(),
        "correction": correction,
        "old_engine": old_engine,
        "new_engine": new_engine,
        "daily_changes": daily_changes,
        "weekly_changes": weekly_changes,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if _sha256(baseline_path) != baseline_sha:
        raise RuntimeError("data.json changed while building correction candidate")

    print(json.dumps({
        "status": "historical correction candidate verified",
        "baseline_unchanged": True,
        "reintroduced_station_days": len(changed),
        "unique_stations": len(correction["unique_station_ids"]),
        "daily_rows_changed": len(daily_changes),
        "weekly_rows_changed": len(weekly_changes),
        "candidate_sha256": report["candidate_sha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
