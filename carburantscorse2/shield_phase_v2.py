#!/usr/bin/env python3
"""Read explicit effective-shield cap phases published by C1.

C2 does not redetect the shield and does not derive phases from Rotterdam. It
consumes the phase list produced upstream by C1 from the independent shield rule
and TotalEnergies cap schedule. Invalid or legacy manifests fail explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Mapping


@dataclass(frozen=True)
class ShieldPhase:
    fuel: str
    started_on: date
    ended_on: date
    cap: float
    phase_id: str


def validated_phases(bouclier_metadata: Mapping, fuel: str) -> tuple[ShieldPhase, ...]:
    if not isinstance(bouclier_metadata, Mapping):
        raise RuntimeError("C1 bouclier metadata is missing or invalid")
    fuel_meta = bouclier_metadata.get(fuel)
    if not isinstance(fuel_meta, Mapping):
        raise RuntimeError(f"C1 bouclier metadata has no {fuel} section")
    if "phases" not in fuel_meta:
        raise RuntimeError(f"C1 bouclier metadata for {fuel} has no cap phases")
    raw_phases = fuel_meta.get("phases")
    if not isinstance(raw_phases, list):
        raise RuntimeError(f"C1 cap phases for {fuel} are not a list")

    phases: list[ShieldPhase] = []
    seen_ids: set[str] = set()
    for item in raw_phases:
        if not isinstance(item, Mapping):
            raise RuntimeError(f"Invalid C1 shield phase entry for {fuel}")
        try:
            start = date.fromisoformat(str(item["d1"]))
            end = date.fromisoformat(str(item["d2"]))
            cap = float(item["cap"])
            phase_id = str(item["phase_id"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid C1 shield phase for {fuel}") from exc
        if end < start:
            raise RuntimeError(f"C1 shield phase ends before it starts for {fuel}")
        if not math.isfinite(cap):
            raise RuntimeError(f"C1 shield phase has a non-finite cap for {fuel}")
        if not phase_id or phase_id in seen_ids:
            raise RuntimeError(f"C1 shield phase_id missing or duplicated for {fuel}")
        seen_ids.add(phase_id)
        phases.append(ShieldPhase(fuel, start, end, cap, phase_id))

    phases.sort(key=lambda phase: (phase.started_on, phase.ended_on, phase.phase_id))
    for previous, current in zip(phases, phases[1:]):
        if current.started_on <= previous.ended_on:
            raise RuntimeError(f"C1 shield phases overlap for {fuel}")
    return tuple(phases)


def phase_for_day(bouclier_metadata: Mapping, fuel: str, day: date) -> ShieldPhase | None:
    for phase in validated_phases(bouclier_metadata, fuel):
        if phase.started_on <= day <= phase.ended_on:
            return phase
    return None
