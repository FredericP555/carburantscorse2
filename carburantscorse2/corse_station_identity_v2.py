#!/usr/bin/env python3
"""Prepared C2 guard for Corsica station identity.

This module is intentionally not imported by publication.py.  Brand-sensitive
candidate calculations may use it to distinguish confirmed TotalEnergies,
confirmed non-Total and unresolved Corsica station IDs.

The source of truth is C1's ``config/corse_station_brands.json``.  C2 must not
maintain a divergent copy of the Corsica brand registry.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_REGISTRY_FILE = Path("outputs/c1/corse_station_brands.json")
EXPECTED_SCHEMA = "a4c-corsica-station-brands-v2"

TOTAL = "TOTAL"
NON_TOTAL_CONFIRMED = "NON_TOTAL_CONFIRMED"
UNKNOWN = "UNKNOWN"


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").casefold().replace("é", "e").split())


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
    """Return TOTAL, NON_TOTAL_CONFIRMED or UNKNOWN for one Corsica ID.

    Missing IDs and entries explicitly marked ``inconnu`` fail closed to UNKNOWN.
    A resolved non-Total brand is NON_TOTAL_CONFIRMED; it is never inferred merely
    because the ID is absent from the Total list.
    """
    entry = (registry.get("stations") or {}).get(str(station_id))
    if not isinstance(entry, dict):
        return UNKNOWN

    segment = str(entry.get("segment") or "").strip()
    brand = str(entry.get("enseigne") or "").strip()
    brand_source = str(entry.get("brand_source") or "").strip()
    if not brand or segment == "inconnu" or brand_source == "non_resolu":
        return UNKNOWN

    normalized = _norm(brand)
    if "totalenergies" in normalized or normalized == "total" or normalized.startswith("total "):
        return TOTAL
    return NON_TOTAL_CONFIRMED


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
