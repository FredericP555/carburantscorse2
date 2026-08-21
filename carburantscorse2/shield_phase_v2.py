#!/usr/bin/env python3
"""Read explicit effective-shield cap phases published by C1.

C2 does not redetect the shield and does not derive phases from Rotterdam. It
consumes the phase list produced upstream by C1 from the independent shield rule
and TotalEnergies cap schedule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping


@dataclass(frozen=True)
class ShieldPhase:
    fuel: str
    started_on: date
    ended_on: date
    cap: float
    phase_id: str | None = None


def phase_for_day(bouclier_metadata: Mapping, fuel: str, day: date) -> ShieldPhase | None:
    fuel_meta = bouclier_metadata.get(fuel, {}) if isinstance(bouclier_metadata, Mapping) else {}
    phases = fuel_meta.get("phases", []) if isinstance(fuel_meta, Mapping) else []
    for item in phases:
        if not isinstance(item, Mapping):
            continue
        try:
            start = date.fromisoformat(str(item["d1"]))
            end = date.fromisoformat(str(item["d2"]))
            cap = float(item["cap"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid C1 shield phase for {fuel}") from exc
        if start <= day <= end:
            return ShieldPhase(
                fuel=fuel,
                started_on=start,
                ended_on=end,
                cap=cap,
                phase_id=str(item.get("phase_id")) if item.get("phase_id") else None,
            )
    return None
