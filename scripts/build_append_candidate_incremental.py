#!/usr/bin/env python3
"""Run the normal append-only build with incremental BDR station classification.

The shared official observations are already loaded by the normal builder. This wrapper reuses
those same rows to resolve only BDR IDs not present in the frozen 2026 category table, then
injects the incremental categories before the published series are calculated.

If a new ID cannot yet be resolved, it remains category=unknown: it still participates in the
'all BDR' comparison, but is excluded from the network-only comparison until a later run can
resolve its official brand. Publication therefore continues instead of blocking on one orphan ID.
"""
from __future__ import annotations

import json
from pathlib import Path

from carburantscorse2.publication import unknown_recent_bdr_stations as detect_unknown
from scripts import build_append_candidate as base
from scripts.resolve_new_bdr_station_brands import (
    DEFAULT_CORRECTIONS,
    DEFAULT_REGISTRY,
    load_registry,
    resolve_from_observations,
    resolved_categories,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_CATEGORIES = ROOT / "config" / "bdr_categories_published_2026-06-06.csv"

_original_load_official = base.load_official_observations
_original_load_categories = base.load_bdr_categories


def _merged_categories(path):
    legacy = _original_load_categories(path)
    incremental = resolved_categories(load_registry(DEFAULT_REGISTRY))
    # Frozen published category always wins for pre-existing IDs. Incremental rules only apply
    # to IDs first encountered after that legacy registry was frozen.
    for station_id, category in incremental.items():
        legacy.setdefault(station_id, category)
    return legacy


def _load_official_and_resolve(years, mode):
    observations, source = _original_load_official(years, mode)
    legacy = _original_load_categories(LEGACY_CATEGORIES)
    summary = resolve_from_observations(
        observations,
        legacy,
        registry_path=DEFAULT_REGISTRY,
        corrections_path=DEFAULT_CORRECTIONS,
    )
    print("Incremental BDR station-brand resolution:")
    print(json.dumps({k: v for k, v in summary.items() if k != "categories"}, ensure_ascii=False, indent=2))
    return observations, source


def _non_blocking_unknown(state, *, since):
    unknown = detect_unknown(state, since=since)
    if unknown:
        print(
            "WARNING: unresolved recent BDR station IDs are excluded from the network-only "
            f"comparison until resolved: {', '.join(unknown)}"
        )
    # The unresolved IDs remain category=unknown in state. Returning [] here only disables the
    # old publication blocker; it does not silently classify them as network or GMS.
    return []


base.load_official_observations = _load_official_and_resolve
base.load_bdr_categories = _merged_categories
base.unknown_recent_bdr_stations = _non_blocking_unknown


if __name__ == "__main__":
    base.main()
