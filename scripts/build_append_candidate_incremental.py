#!/usr/bin/env python3
"""Run the normal append-only build with incremental BDR station classification.

The shared official observations are already loaded by the normal builder. This wrapper reuses
those same rows to resolve only BDR IDs not present in the frozen 2026 category table, then
injects the incremental categories before the published series are calculated.

Only IDs seen in the latest 30-day BDR activity window are candidates for a lookup. This matches
the publication's BDR carry/inactivity horizon and avoids chasing obsolete historical IDs.

If a new ID cannot yet be resolved, it remains category=unknown: it still participates in the
'all BDR' comparison, but is excluded from the network-only comparison until a later run can
resolve its official brand. Publication therefore continues instead of blocking on one orphan ID.
"""
from __future__ import annotations

from datetime import timedelta
import json
import math
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
BDR_ACTIVE_WINDOW_DAYS = 30

_original_load_official = base.load_official_observations
_original_load_categories = base.load_bdr_categories
_original_load_rotterdam = base.load_shared_rotterdam


def _merged_categories(path):
    legacy = _original_load_categories(path)
    incremental = resolved_categories(load_registry(DEFAULT_REGISTRY))
    for station_id, category in incremental.items():
        legacy.setdefault(station_id, category)
    return legacy


def _recent_bdr_observations(observations):
    bdr = [
        row for row in observations
        if str(row.get("department") or "") == "13"
        and not bool(row.get("is_motorway"))
        and str(row.get("pop") or "") != "A"
    ]
    if not bdr:
        return []
    latest = max(row["date"] for row in bdr)
    cutoff = latest - timedelta(days=BDR_ACTIVE_WINDOW_DAYS)
    return [row for row in bdr if row["date"] >= cutoff]


def _load_official_and_resolve(years, mode, *, release_tag=None):
    """Preserve the single C1 release selected at workflow start."""
    observations, source = _original_load_official(
        years,
        mode,
        release_tag=release_tag,
    )
    legacy = _original_load_categories(LEGACY_CATEGORIES)
    recent = _recent_bdr_observations(observations)
    summary = resolve_from_observations(
        recent,
        legacy,
        registry_path=DEFAULT_REGISTRY,
        corrections_path=DEFAULT_CORRECTIONS,
    )
    print("Incremental BDR station-brand resolution:")
    print(json.dumps({k: v for k, v in summary.items() if k != "categories"}, ensure_ascii=False, indent=2))
    return observations, source


def _load_shared_rotterdam_finite(start, end):
    """Fail closed if a shared Rotterdam frame contains NaN or +/-Inf."""
    daily, observed = _original_load_rotterdam(start, end)
    for name, frame in (("daily", daily), ("observed", observed)):
        values = frame["rotterdam_eur_l"]
        ok = values.map(lambda value: math.isfinite(float(value))).all()
        if not bool(ok):
            raise RuntimeError(f"Shared Rotterdam {name} CSV contains a non-finite value")
    return daily, observed


def _non_blocking_unknown(state, *, since):
    unknown = detect_unknown(state, since=since)
    if unknown:
        print(
            "WARNING: unresolved recent BDR station IDs are excluded from the network-only "
            f"comparison until resolved: {', '.join(unknown)}"
        )
    return []


base.load_official_observations = _load_official_and_resolve
base.load_bdr_categories = _merged_categories
base.load_shared_rotterdam = _load_shared_rotterdam_finite
base.unknown_recent_bdr_stations = _non_blocking_unknown


if __name__ == "__main__":
    base.main()
