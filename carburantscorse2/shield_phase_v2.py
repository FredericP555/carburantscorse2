#!/usr/bin/env python3
"""Read explicit effective-shield cap phases published by C1."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import math
from typing import Mapping

@dataclass(frozen=True)
class ShieldPhase:
    fuel: str; started_on: date; ended_on: date; cap: float; phase_id: str

@dataclass(frozen=True)
class DoubleCapPeriod:
    started_on: date; ended_on: date; gazole_cap: float; sp95_cap: float

def validated_phases(bouclier_metadata: Mapping, fuel: str) -> tuple[ShieldPhase, ...]:
    if not isinstance(bouclier_metadata, Mapping): raise RuntimeError("C1 bouclier metadata is missing or invalid")
    fuel_meta = bouclier_metadata.get(fuel)
    if not isinstance(fuel_meta, Mapping): raise RuntimeError(f"C1 bouclier metadata has no {fuel} section")
    if "phases" not in fuel_meta: raise RuntimeError(f"C1 bouclier metadata for {fuel} has no cap phases")
    raw_phases = fuel_meta.get("phases")
    if not isinstance(raw_phases, list): raise RuntimeError(f"C1 cap phases for {fuel} are not a list")
    phases=[]; seen_ids=set()
    for item in raw_phases:
        if not isinstance(item, Mapping): raise RuntimeError(f"Invalid C1 shield phase entry for {fuel}")
        try:
            start=date.fromisoformat(str(item["d1"])); end=date.fromisoformat(str(item["d2"])); cap=float(item["cap"]); phase_id=str(item["phase_id"]).strip()
        except (KeyError,TypeError,ValueError) as exc: raise RuntimeError(f"Invalid C1 shield phase for {fuel}") from exc
        if end < start: raise RuntimeError(f"C1 shield phase ends before it starts for {fuel}")
        if not math.isfinite(cap): raise RuntimeError(f"C1 shield phase has a non-finite cap for {fuel}")
        if not phase_id or phase_id in seen_ids: raise RuntimeError(f"C1 shield phase_id missing or duplicated for {fuel}")
        seen_ids.add(phase_id); phases.append(ShieldPhase(fuel,start,end,cap,phase_id))
    phases.sort(key=lambda p:(p.started_on,p.ended_on,p.phase_id))
    for previous,current in zip(phases,phases[1:]):
        if current.started_on <= previous.ended_on: raise RuntimeError(f"C1 shield phases overlap for {fuel}")
    return tuple(phases)

def phase_for_day(bouclier_metadata: Mapping, fuel: str, day: date) -> ShieldPhase | None:
    for phase in validated_phases(bouclier_metadata,fuel):
        if phase.started_on <= day <= phase.ended_on: return phase
    return None

def double_cap_period_for_day(bouclier_metadata: Mapping, day: date) -> DoubleCapPeriod | None:
    gazole=phase_for_day(bouclier_metadata,"Gazole",day); sp95=phase_for_day(bouclier_metadata,"SP95",day)
    if gazole is None or sp95 is None: return None
    start=max(gazole.started_on,sp95.started_on); end=min(gazole.ended_on,sp95.ended_on)
    if not (start <= day <= end): return None
    return DoubleCapPeriod(start,end,gazole.cap,sp95.cap)
