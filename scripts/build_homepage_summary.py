#!/usr/bin/env python3
"""Build a public, read-only weekly summary from the production C2 dataset.

This script is deliberately downstream of the production pipeline:
- it never writes or promotes ``data.json``;
- it reuses the exact C1 release pinned in production ``data.json``;
- it reuses the existing C2 V2 eligibility engine;
- it validates its latest published gaps against ``data.json`` before writing output.

The resulting ``homepage-summary.json`` is intended for lightweight consumers such as
fpoletti.fr. A failure here must never block or roll back C1/C2 production.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_publication_state
from scripts.build_v2_production_candidate import (
    C1_META,
    CORSE_REGISTRY,
    ROOT,
    SWITCH_DAY,
    WEEKLY_SWITCH,
    _evaluate_v2,
    _merged_bdr_categories,
)
from scripts.v2_event_guards import EventGuards

TAG_PREFIX = "a4c-v2-shared-"
SCHEMA = "a4c-homepage-summary-v1"
FUELS = {
    "Gazole": ("gazole", "sp95"),
    "SP95": ("sp95", "sp95"),
}
SCOPES = {
    "all": "all",
    "network": "reseau",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data.json")
    p.add_argument("--output", default="homepage-summary.json")
    return p.parse_args()


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, digits: int = 4) -> float | None:
    out = _finite(value)
    return None if out is None else round(out, digits)


def _periodize(frame: pd.DataFrame, granularity: str) -> pd.DataFrame:
    out = frame.copy()
    if granularity == "daily":
        out["period"] = out["date"]
    elif granularity == "weekly":
        out["period"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    else:
        raise ValueError("granularity must be daily or weekly")
    return out


def _build_level_series(
    state: pd.DataFrame,
    *,
    fuel: str,
    scope: str,
    granularity: str,
    through: date,
    lookback_days: int,
    min_corse_stations: int = 5,
    min_bdr_stations: int = 10,
) -> list[dict]:
    if scope not in {"all", "network"}:
        raise ValueError("scope must be all or network")
    start = pd.Timestamp(through - timedelta(days=lookback_days))
    end = pd.Timestamp(through)
    reliable = state[
        state["eligible_publication"]
        & (state["date"] >= start)
        & (state["date"] <= end)
    ].copy()
    corse = reliable[(reliable["territory"] == "Corse") & (reliable["fuel"] == fuel)].copy()
    bdr_all = reliable[(reliable["territory"] == "Bouches-du-Rhone") & (reliable["fuel"] == fuel)].copy()
    bdr = bdr_all if scope == "all" else bdr_all[bdr_all["category"] == "network"].copy()

    corse = _periodize(corse, granularity)
    bdr = _periodize(bdr, granularity)
    bdr_all = _periodize(bdr_all, granularity)

    cg = corse.groupby("period").agg(
        corse_ht=("price_ht", "mean"),
        corse_ttc=("price", "mean"),
        n_corse=("station_id", "nunique"),
    )
    bg = bdr.groupby("period").agg(
        bdr_ht=("price_ht", "mean"),
        bdr_ttc=("price", "mean"),
        n_bdr_scope=("station_id", "nunique"),
    )
    guard = bdr_all.groupby("period").agg(n_bdr_guard=("station_id", "nunique"))
    merged = cg.join(bg, how="inner").join(guard, how="left")
    merged = merged[
        (merged["n_corse"] >= min_corse_stations)
        & (merged["n_bdr_guard"] >= min_bdr_stations)
    ]

    result: list[dict] = []
    for period, row in merged.sort_index().iterrows():
        period_day = pd.Timestamp(period).date()
        if granularity == "weekly" and period_day + timedelta(days=6) > through:
            continue
        result.append(
            {
                "date": period_day.isoformat(),
                "corse_ht_eur_l": _round(row["corse_ht"], 4),
                "corse_ttc_eur_l": _round(row["corse_ttc"], 4),
                "bdr_ht_eur_l": _round(row["bdr_ht"], 4),
                "bdr_ttc_eur_l": _round(row["bdr_ttc"], 4),
                "gap_ht_c_l": round((float(row["corse_ht"]) - float(row["bdr_ht"])) * 100.0, 2),
                "n_corse": int(row["n_corse"]),
                "n_bdr": int(row["n_bdr_scope"]),
                "n_bdr_guard": int(row["n_bdr_guard"]),
            }
        )
    return result


def _find_row(series: list[dict], day: date) -> dict | None:
    target = day.isoformat()
    for row in reversed(series):
        if str(row.get("date")) == target:
            return deepcopy(row)
    return None


def _comparison_metrics(series: list[dict]) -> dict:
    if not series:
        raise RuntimeError("Cannot summarize an empty series")
    latest = deepcopy(series[-1])
    previous = deepcopy(series[-2]) if len(series) >= 2 else None
    latest_day = date.fromisoformat(str(latest["date"]))
    four_weeks_ago = _find_row(series, latest_day - timedelta(days=28))
    year_ago = _find_row(series, latest_day - timedelta(days=364))

    def delta(other: dict | None) -> float | None:
        if other is None:
            return None
        return round(float(latest["gap_ht_c_l"]) - float(other["gap_ht_c_l"]), 2)

    return {
        "latest": latest,
        "previous": previous,
        "gap_change_wow_c_l": delta(previous),
        "four_weeks_ago": four_weeks_ago,
        "gap_change_4w_c_l": delta(four_weeks_ago),
        "year_ago": year_ago,
        "gap_change_yoy_c_l": delta(year_ago),
        "recent": deepcopy(series[-8:]),
    }


def _published_series(data: dict, fuel: str, granularity: str, scope: str) -> list[dict]:
    key, ref = FUELS[fuel]
    published_scope = SCOPES[scope]
    return data["DATA"][key][ref][granularity][published_scope]


def _assert_gap_match(data: dict, fuel: str, granularity: str, scope: str, generated: list[dict]) -> None:
    published = {str(row["date"]): float(row["ecart"]) for row in _published_series(data, fuel, granularity, scope)}
    for row in generated[-2:]:
        day = str(row["date"])
        if day not in published:
            raise RuntimeError(f"Summary {fuel}/{granularity}/{scope} date {day} is absent from published data.json")
        actual = float(row["gap_ht_c_l"])
        expected = published[day]
        if abs(actual - expected) > 0.005:
            raise RuntimeError(
                f"Summary gap mismatch for {fuel}/{granularity}/{scope}/{day}: "
                f"summary={actual:.2f} published={expected:.2f}"
            )


def _margin_summary(data: dict, group: str) -> dict:
    rows = list((data.get("MARGES_GZ") or {}).get(group) or [])
    if not rows:
        return {"latest": None, "previous": None, "recent": []}
    return {
        "latest": deepcopy(rows[-1]),
        "previous": deepcopy(rows[-2]) if len(rows) >= 2 else None,
        "recent": deepcopy(rows[-8:]),
    }


def build_summary(data: dict) -> dict:
    meta = dict(data.get("meta") or {})
    v2 = dict(meta.get("v2") or {})
    if not v2.get("active"):
        raise RuntimeError("Production data.json is not marked V2 active")
    if v2.get("daily_switch_date") != SWITCH_DAY.isoformat():
        raise RuntimeError("Unexpected V2 daily switch date")
    if v2.get("weekly_switch_date") != WEEKLY_SWITCH.isoformat():
        raise RuntimeError("Unexpected V2 weekly switch date")

    release_tag = str(v2.get("c1_release_tag") or meta.get("official_shared_release_tag") or "")
    if not release_tag.startswith(TAG_PREFIX):
        raise RuntimeError(f"Unexpected or missing C1 V2 production release tag: {release_tag!r}")

    target_end = date.fromisoformat(str(meta["daily_target_end"]))
    weekly_end = date.fromisoformat(str(meta["weekly_complete_through"]))
    download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix=TAG_PREFIX,
        release_tag=release_tag,
        registry_output=CORSE_REGISTRY,
        tag_output=ROOT / "outputs" / "c1" / "shared_release_tag.txt",
    )
    c1_meta = json.loads(C1_META.read_text(encoding="utf-8"))
    years = sorted(int(y) for y in c1_meta.get("years", []))
    observations, source = load_shared_observations(
        years,
        tag_prefix=TAG_PREFIX,
        release_tag=release_tag,
    )
    source_max = date.fromisoformat(str(source.get("shared_source_max_date")))
    if source_max < target_end:
        raise RuntimeError(f"Pinned C1 release is older than published C2 data: {source_max} < {target_end}")

    categories = _merged_bdr_categories()
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(target_end),
        bdr_categories=categories,
    )
    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")
    guards = EventGuards.from_release(release_tag, metadata=c1_meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    v2_state, engine = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=SWITCH_DAY,
        end=target_end,
    )

    fuels: dict[str, dict] = {}
    for fuel in FUELS:
        fuels[fuel] = {}
        for scope in SCOPES:
            daily = _build_level_series(
                v2_state,
                fuel=fuel,
                scope=scope,
                granularity="daily",
                through=target_end,
                lookback_days=40,
            )
            weekly = _build_level_series(
                v2_state,
                fuel=fuel,
                scope=scope,
                granularity="weekly",
                through=weekly_end,
                lookback_days=430,
            )
            _assert_gap_match(data, fuel, "daily", scope, daily)
            _assert_gap_match(data, fuel, "weekly", scope, weekly)
            fuels[fuel][scope] = {
                "daily": _comparison_metrics(daily),
                "weekly": _comparison_metrics(weekly),
            }

    homepage = {
        "comparison": "Corse vs Bouches-du-Rhone - reseau traditionnel",
        "period": "latest_complete_week",
        "week_start": fuels["Gazole"]["network"]["weekly"]["latest"]["date"],
        "week_end": weekly_end.isoformat(),
        "gazole": {
            "gap_ht_c_l": fuels["Gazole"]["network"]["weekly"]["latest"]["gap_ht_c_l"],
            "gap_change_wow_c_l": fuels["Gazole"]["network"]["weekly"]["gap_change_wow_c_l"],
        },
        "sp95": {
            "gap_ht_c_l": fuels["SP95"]["network"]["weekly"]["latest"]["gap_ht_c_l"],
            "gap_change_wow_c_l": fuels["SP95"]["network"]["weekly"]["gap_change_wow_c_l"],
        },
    }

    warnings: list[str] = []
    if int(engine.get("r2_unavailable", 0)):
        warnings.append(f"r2_unavailable={int(engine.get('r2_unavailable', 0))}")
    unknown = list(meta.get("unknown_recent_bdr_stations") or [])
    if unknown:
        warnings.append(f"unknown_recent_bdr_stations={len(unknown)}")

    return {
        "schema": SCHEMA,
        "generated_at": meta.get("generated_at"),
        "homepage_default": homepage,
        "source": {
            "daily_data_through": target_end.isoformat(),
            "weekly_data_through": weekly_end.isoformat(),
            "official_source_max_date": meta.get("official_source_max_date"),
            "c1_release_tag": release_tag,
            "c1_release_published_at": meta.get("official_shared_release_published_at"),
            "c1_snapshot_sha256": meta.get("official_shared_sha256"),
            "ufip_last_observed_date": meta.get("ufip_last_observed_date"),
        },
        "methodology": {
            "v2_version": v2.get("version"),
            "daily_switch_date": SWITCH_DAY.isoformat(),
            "weekly_switch_date": WEEKLY_SWITCH.isoformat(),
            "history_through_2026_07_22_preserved": bool(v2.get("history_before_switch_preserved")),
            "weekly_overlap_2026_07_20_preserved": bool(v2.get("weekly_overlap_2026_07_20_preserved")),
            "comparison_default": "network",
        },
        "fuels": fuels,
        "shield": deepcopy(meta.get("bouclier") or {}),
        "margin_gazole": {
            "all": _margin_summary(data, "all"),
            "network": _margin_summary(data, "reseau"),
            "ufip_last_observed_date": meta.get("ufip_last_observed_date"),
        },
        "quality": {
            "unknown_recent_bdr_station_ids": unknown,
            "r2_calls": int(engine.get("r2_calls", 0)),
            "r2_unavailable": int(engine.get("r2_unavailable", 0)),
            "warnings": warnings,
        },
    }


def main() -> None:
    args = parse_args()
    data_path = ROOT / args.data
    output_path = ROOT / args.output
    data = json.loads(data_path.read_text(encoding="utf-8"))
    summary = build_summary(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["homepage_default"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
