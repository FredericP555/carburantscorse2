#!/usr/bin/env python3
"""Prepared C2 guard for Corsica station identity.

The source of truth is C1's ``config/corse_station_brands.json``. C2 consumes the
registry bundled in the pinned C1 release and uses the exact same tri-state
classification semantics as C1.
"""
from __future__ import annotations

import json
from pathlib import Path

from a4c_common.corse_brand import (
    NON_TOTAL_CONFIRMED,
    TOTAL,
    UNKNOWN,
    classify_registry_entry,
)

DEFAULT_REGISTRY_FILE = Path("outputs/c1/corse_station_brands.json")
EXPECTED_SCHEMA = "a4c-corsica-station-brands-v2"


def load_registry(path: str | Path = DEFAULT_REGISTRY_FILE) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != EXPECTED_SCHEMA:
        raise RuntimeError(
            f"Unexpected C1 Corsica brand registry schema: {payload.get('schema')!r}"
        )
    if not isinstance(payload.get("stations"), dict):
        raise RuntimeError("C1 Corsica brand registry has no stations mapping")
    return payload


def classify_station_id(station_id: str, registry: dict) -> str:
    """Return TOTAL, NON_TOTAL_CONFIRMED or UNKNOWN for one Corsica ID."""
    entry = (registry.get("stations") or {}).get(str(station_id))
    return classify_registry_entry(entry)


def classify_from_file(
    station_id: str,
    path: str | Path = DEFAULT_REGISTRY_FILE,
) -> str:
    return classify_station_id(station_id, load_registry(path))


def split_station_ids(station_ids, registry: dict) -> dict[str, set[str]]:
    groups = {TOTAL: set(), NON_TOTAL_CONFIRMED: set(), UNKNOWN: set()}
    for raw in station_ids:
        station_id = str(raw)
        groups[classify_station_id(station_id, registry)].add(station_id)
    return groups
