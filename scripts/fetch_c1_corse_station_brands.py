#!/usr/bin/env python3
"""Fetch C1's Corsica station-brand registry for prepared C2 calculations.

Read-only with respect to C1 and C2 repositories: the file is written only to
``outputs/`` in the current workflow workspace and may be archived as an audit
artifact.  It is not committed by the weekly publication step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.request

DEFAULT_URL = (
    "https://raw.githubusercontent.com/FredericP555/"
    "carburantscorse1/main/config/corse_station_brands.json"
)
EXPECTED_SCHEMA = "a4c-corsica-station-brands-v2"


def fetch_registry(url: str = DEFAULT_URL, *, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "A4C-carburantscorse2/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("schema") != EXPECTED_SCHEMA:
        raise RuntimeError(
            f"Unexpected C1 Corsica brand registry schema: {payload.get('schema')!r}"
        )
    stations = payload.get("stations")
    if not isinstance(stations, dict) or not stations:
        raise RuntimeError("C1 Corsica brand registry contains no stations")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="outputs/c1/corse_station_brands.json",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    payload = fetch_registry(args.url)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stations = payload["stations"]
    unresolved = sum(
        1
        for entry in stations.values()
        if not isinstance(entry, dict)
        or entry.get("segment") == "inconnu"
        or not entry.get("enseigne")
    )
    print(f"C1 Corsica brand registry: {len(stations)} IDs; unresolved={unresolved}")
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
