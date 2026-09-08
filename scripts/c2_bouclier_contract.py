#!/usr/bin/env python3
"""Fail-closed C2 contract for C1-owned effective-shield metadata."""
from __future__ import annotations

from datetime import date, timedelta
import math

from carburantscorse2 import shield_phase_v2

REQUIRED_FUELS = ("Gazole", "SP95")
PRICE_MIN = 1.10
PRICE_MAX = 3.00


def _fail(message: str) -> None:
    raise ValueError(message)


def _as_date(value, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}={value!r}") from exc


def _finite(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric {label}={value!r}") from exc
    if not math.isfinite(number):
        _fail(f"non-finite {label}={value!r}")
    return number


def validate_bouclier_contract(meta: dict, *, source_max: date, target_end: date) -> None:
    bmeta = meta.get("bouclier")
    if not isinstance(bmeta, dict):
        _fail("missing bouclier metadata")

    for fuel in REQUIRED_FUELS:
        node = bmeta.get(fuel)
        if not isinstance(node, dict):
            _fail(f"missing bouclier metadata for {fuel}")
        for field in ("ranges", "phases", "current_active", "current_active_since", "current_cap"):
            if field not in node:
                _fail(f"bouclier.{fuel}.{field} missing")
        if not isinstance(node["ranges"], list):
            _fail(f"bouclier.{fuel}.ranges is not a list")
        if not isinstance(node["phases"], list):
            _fail(f"bouclier.{fuel}.phases is not a list")
        if not isinstance(node["current_active"], bool):
            _fail(f"bouclier.{fuel}.current_active is not boolean")

        ranges: list[tuple[date, date]] = []
        previous_end: date | None = None
        for index, item in enumerate(node["ranges"]):
            if not isinstance(item, dict):
                _fail(f"bouclier.{fuel}.ranges[{index}] is not an object")
            start = _as_date(item.get("d1"), f"bouclier.{fuel}.ranges[{index}].d1")
            end = _as_date(item.get("d2"), f"bouclier.{fuel}.ranges[{index}].d2")
            if start > end:
                _fail(f"bouclier.{fuel}: inverted range {item!r}")
            if previous_end is not None and start <= previous_end:
                _fail(f"bouclier.{fuel}: overlapping/unordered ranges")
            if end > source_max:
                _fail(f"bouclier.{fuel}: range ends after official source max date")
            ranges.append((start, end))
            previous_end = end

        try:
            phases = list(shield_phase_v2.validated_phases(bmeta, fuel))
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

        for phase in phases:
            if not PRICE_MIN <= phase.cap <= PRICE_MAX:
                _fail(
                    f"bouclier.{fuel}: phase cap {phase.cap:.3f} outside "
                    f"{PRICE_MIN:.2f}-{PRICE_MAX:.2f} €/L"
                )
            if phase.ended_on > source_max:
                _fail(f"bouclier.{fuel}: phase ends after official source max date")
            containing = [r for r in ranges if r[0] <= phase.started_on and phase.ended_on <= r[1]]
            if len(containing) != 1:
                _fail(f"bouclier.{fuel}: phase lies outside effective ranges")

        for start, end in ranges:
            covered = [p for p in phases if start <= p.started_on and p.ended_on <= end]
            if not covered:
                _fail(f"bouclier.{fuel}: range {start}..{end} has no cap phase")
            if covered[0].started_on != start or covered[-1].ended_on != end:
                _fail(f"bouclier.{fuel}: cap phases do not cover range {start}..{end}")
            for previous, current in zip(covered, covered[1:]):
                if current.started_on != previous.ended_on + timedelta(days=1):
                    _fail(f"bouclier.{fuel}: cap phase gap inside range {start}..{end}")

        evaluated_raw = node.get("evaluated_through")
        evaluated = target_end if evaluated_raw is None else _as_date(
            evaluated_raw, f"bouclier.{fuel}.evaluated_through"
        )
        if evaluated > source_max:
            _fail(f"bouclier.{fuel}.evaluated_through exceeds official source max date")
        if evaluated < target_end:
            _fail(f"bouclier.{fuel}.evaluated_through predates daily_target_end")

        covering = next((r for r in ranges if r[0] <= evaluated <= r[1]), None)
        active_phase = next(
            (p for p in phases if p.started_on <= evaluated <= p.ended_on), None
        )
        if node["current_active"]:
            if covering is None:
                _fail(f"bouclier.{fuel}: active but no effective range covers {evaluated}")
            if active_phase is None:
                _fail(f"bouclier.{fuel}: active but no cap phase covers {evaluated}")
            active_since = _as_date(
                node["current_active_since"], f"bouclier.{fuel}.current_active_since"
            )
            if active_since != covering[0]:
                _fail(
                    f"bouclier.{fuel}: current_active_since={active_since} does not match "
                    f"covering range start {covering[0]}"
                )
            current_cap = _finite(node["current_cap"], f"bouclier.{fuel}.current_cap")
            if not PRICE_MIN <= current_cap <= PRICE_MAX:
                _fail(f"bouclier.{fuel}: current_cap outside published price band")
            if abs(current_cap - active_phase.cap) > 1e-9:
                _fail(
                    f"bouclier.{fuel}: current_cap={current_cap:.3f} does not match "
                    f"active phase cap {active_phase.cap:.3f}"
                )
            at_cap = node.get("latest_at_cap_count")
            if at_cap is not None and (not isinstance(at_cap, int) or at_cap < 1):
                _fail(f"bouclier.{fuel}: active without a Total station at cap")
        elif covering is not None or active_phase is not None:
            _fail(f"bouclier.{fuel}: inactive while an effective range/phase covers {evaluated}")
