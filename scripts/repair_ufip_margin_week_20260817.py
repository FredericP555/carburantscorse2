#!/usr/bin/env python3
"""One-time guarded repair of the 17 Aug 2026 apparent-margin week.

The 24 Aug production run fetched UFIP before the prior week's Rotterdam quotations
had been published, so the legacy forward-fill created a provisional margin week from
the 14 Aug quote. This script has strict preconditions and rewrites only that final
margin period after UFIP genuinely covers 17-21 Aug. It does not alter price-gap series.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole
from carburantscorse2.publication import build_publication_state, load_bdr_categories
from carburantscorse2.publication_margin import build_margin_series, observed_week_is_complete
from scripts import build_append_candidate as base
from scripts.resolve_new_bdr_station_brands import (
    DEFAULT_REGISTRY as BDR_REGISTRY,
    load_registry,
    resolved_categories,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.json"
LEGACY_CATEGORIES = ROOT / "config" / "bdr_categories_published_2026-06-06.csv"
WEEK_START = pd.Timestamp("2026-08-17")
WEEK_END = WEEK_START + pd.Timedelta(6, unit="D")
EXPECTED_OLD_UFIP_LAST = pd.Timestamp("2026-08-14")


def _merged_bdr_categories() -> dict[str, str]:
    categories = load_bdr_categories(LEGACY_CATEGORIES)
    incremental = resolved_categories(load_registry(BDR_REGISTRY))
    for station_id, category in incremental.items():
        categories.setdefault(str(station_id), category)
    return categories


def _replace_last_week(rows: list[dict], replacement: dict, group: str) -> None:
    if not rows or pd.Timestamp(rows[-1]["date"]).normalize() != WEEK_START:
        raise RuntimeError(f"{group}: expected final margin week {WEEK_START.date()}")
    if replacement.get("date") != WEEK_START.strftime("%Y-%m-%d"):
        raise RuntimeError(f"{group}: generated replacement has wrong date")
    rows[-1] = replacement


def main() -> None:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    meta = payload.get("meta") or {}
    current_ufip_last = pd.Timestamp(meta.get("ufip_last_observed_date")).normalize()
    if current_ufip_last > EXPECTED_OLD_UFIP_LAST:
        print(f"Repair already applied or source already newer: {current_ufip_last.date()}")
        return
    if current_ufip_last != EXPECTED_OLD_UFIP_LAST:
        raise RuntimeError(f"Unexpected baseline UFIP date: {current_ufip_last.date()}")

    margins = payload.get("MARGES_GZ") or {}
    for group in ("all", "reseau"):
        rows = margins.get(group) or []
        if not rows or pd.Timestamp(rows[-1]["date"]).normalize() != WEEK_START:
            raise RuntimeError(f"{group}: baseline final margin week is not 2026-08-17")

    # Read the same shared official-price source and the already-resolved BDR registry,
    # but do not perform any station-brand lookup or mutate any registry during this repair.
    observations, source = base.load_official_observations((2025, 2026), "shared")
    source_max = pd.Timestamp(source.get("shared_source_max_date")).normalize()
    if source_max < WEEK_END:
        raise RuntimeError(f"Shared official stock ends at {source_max.date()}, before repair week end")

    categories = _merged_bdr_categories()
    state = build_publication_state(pd.DataFrame(observations), global_end=WEEK_END, bdr_categories=categories)
    margin_state = state[(state["date"] >= WEEK_START) & (state["date"] <= WEEK_END)].copy()

    fetch_start = (WEEK_START - pd.Timedelta(14, unit="D")).date()
    observed = fetch_rotterdam_gazole(fetch_start, WEEK_END.date())
    if not observed_week_is_complete(observed, WEEK_START):
        last = None if observed.empty else pd.to_datetime(observed["date"]).max().date()
        raise RuntimeError(f"UFIP still does not sufficiently cover week 2026-08-17 (last={last})")
    daily = expand_daily(observed, fetch_start, WEEK_END.date())

    replacements: dict[str, dict] = {}
    for scope, group in (("all", "all"), ("network", "reseau")):
        generated = build_margin_series(margin_state, daily, bdr_scope=scope)
        matching = [row for row in generated if row.get("date") == "2026-08-17"]
        if len(matching) != 1:
            raise RuntimeError(f"{group}: expected exactly one corrected margin row, found {len(matching)}")
        replacements[group] = matching[0]

    before = {group: dict(margins[group][-1]) for group in ("all", "reseau")}
    for group in ("all", "reseau"):
        _replace_last_week(margins[group], replacements[group], group)

    ufip_last = pd.to_datetime(observed["date"]).max().date().isoformat()
    meta["ufip_last_observed_date"] = ufip_last
    meta["generated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    meta["margin_repair_2026_08_17"] = {
        "reason": "UFIP quotations for 17-21 Aug were unavailable during the 24 Aug morning production run",
        "ufip_observed_through": ufip_last,
        "previous": before,
        "corrected": replacements,
    }
    payload["meta"] = meta
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"ufip_last_observed_date": ufip_last, "corrected": replacements}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
