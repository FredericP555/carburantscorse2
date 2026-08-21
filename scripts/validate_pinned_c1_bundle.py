#!/usr/bin/env python3
"""Validate the pinned C1 bundle after download and before candidate construction."""
from __future__ import annotations

import json
from pathlib import Path

from carburantscorse2 import corse_station_identity_v2 as identity
from carburantscorse2 import rotterdam_calibration_v2 as rotterdam
from carburantscorse2 import shield_phase_v2 as phases

META = Path("outputs/ufip/c1_shared_meta.json")
TAG = Path("outputs/c1/shared_release_tag.txt")
REGISTRY = Path("outputs/c1/corse_station_brands.json")


def main() -> None:
    if not TAG.exists() or not TAG.read_text(encoding="utf-8").strip():
        raise RuntimeError("Pinned C1 release tag is missing or empty")
    if not META.exists():
        raise RuntimeError("Pinned C1 metadata is missing")

    payload = json.loads(META.read_text(encoding="utf-8"))
    calibration = rotterdam.calibrate_2026("corsica", shared_meta_file=META)
    if calibration.territory != "corsica":
        raise RuntimeError("Pinned C1 Corsica calibration is invalid")

    bouclier = payload.get("bouclier")
    phases.validated_phases(bouclier, "Gazole")
    phases.validated_phases(bouclier, "SP95")

    registry = identity.load_registry(REGISTRY)
    if not registry.get("stations"):
        raise RuntimeError("Pinned C1 Corsica registry is empty")

    print(f"Pinned C1 bundle contract OK: {TAG.read_text(encoding='utf-8').strip()}")


if __name__ == "__main__":
    main()
