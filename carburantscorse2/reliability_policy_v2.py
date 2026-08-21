#!/usr/bin/env python3
"""Prepared, inactive A4C 45-day/shield policy. Not imported by publication.py.

The effective-shield detector is independent from this module. R2 never defines
whether the shield is effective; it only decides whether stale Gazole/SP95 prices
remain admissible in the double-cap case.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from a4c_common.price_math import at_cap, finite_number

NORMAL_MAX_AGE_DAYS = 45
PRINCIPAL_FUELS = frozenset({"Gazole", "SP95"})
VALID_REGION_KINDS = frozenset({"corsica", "mainland"})


@dataclass(frozen=True)
class Decision:
    eligible: bool
    reason: str
    age_days: int | None


def age_days(ts: datetime | None, day: date) -> int | None:
    return None if ts is None else (day - ts.date()).days


def normally_fresh(ts: datetime | None, day: date) -> bool:
    age = age_days(ts, day)
    return age is not None and 0 <= age < NORMAL_MAX_AGE_DAYS


def recent_liveness(
    *, region_kind: str, target_fuel: str,
    activity_by_fuel: Mapping[str, datetime], day: date,
) -> bool:
    """Rolling 45-day liveness for the single-cap case."""
    if region_kind not in VALID_REGION_KINDS:
        raise ValueError("region_kind")
    for fuel, ts in activity_by_fuel.items():
        if fuel == target_fuel:
            continue
        if region_kind == "corsica" and fuel not in PRINCIPAL_FUELS:
            continue
        if normally_fresh(ts, day):
            return True
    return False


def recent_nonprincipal_liveness(
    *, activity_by_fuel: Mapping[str, datetime], day: date,
) -> bool:
    """BdR double-cap liveness: only fuels other than Gazole/SP95 count."""
    for fuel, ts in activity_by_fuel.items():
        if fuel in PRINCIPAL_FUELS:
            continue
        if normally_fresh(ts, day):
            return True
    return False


def declaration_eligible_for_phase(
    last_declared_at: datetime | None,
    phase_started_on: date | None,
) -> bool:
    """No-resurrection guard for the current cap phase."""
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on >= phase_started_on:
        return True
    age_at_entry = (phase_started_on - declared_on).days
    return 0 <= age_at_entry < NORMAL_MAX_AGE_DAYS


def evaluate(
    *, day: date, region_kind: str, target_fuel: str,
    last_declared_at: datetime | None, last_price: float | None,
    latest_price_valid: bool = True, target_rupture_active: bool = False,
    independently_inactive: bool = False, is_total: bool = False,
    shield_effective: bool = False, applicable_cap: float | None = None,
    phase_started_on: date | None = None,
    activity_by_fuel: Mapping[str, datetime] | None = None,
    gazole_price: float | None = None, gazole_cap: float | None = None,
    sp95_price: float | None = None, sp95_cap: float | None = None,
    rotterdam_stale_price_admissible: bool | None = None,
) -> Decision:
    if region_kind not in VALID_REGION_KINDS:
        raise ValueError("region_kind")

    age = age_days(last_declared_at, day)
    # Audit priority is intentional: rupture first, then independent inactivity.
    if target_rupture_active:
        return Decision(False, "rupture_active", age)
    if independently_inactive:
        return Decision(False, "inactive_independant", age)
    if (
        last_declared_at is None or age is None or age < 0
        or not latest_price_valid or not finite_number(last_price)
    ):
        return Decision(False, "prix_ou_date_absent_invalide", age)
    if normally_fresh(last_declared_at, day):
        return Decision(True, "normal_45j", age)

    if target_fuel not in PRINCIPAL_FUELS:
        return Decision(False, "exception_carburant_non_principal", age)
    if not (is_total and shield_effective):
        return Decision(False, "ancien_hors_exception", age)
    if phase_started_on is None or phase_started_on > day:
        return Decision(False, "phase_plafond_absente_ou_invalide", age)
    if not declaration_eligible_for_phase(last_declared_at, phase_started_on):
        return Decision(False, "pas_de_resurrection_a_entree_plafond", age)
    if not at_cap(last_price, applicable_cap):
        return Decision(False, "ancien_pas_au_plafond", age)

    activity_by_fuel = activity_by_fuel or {}
    both_capped = at_cap(gazole_price, gazole_cap) and at_cap(sp95_price, sp95_cap)

    if both_capped:
        if region_kind == "corsica":
            if rotterdam_stale_price_admissible is True:
                return Decision(True, "double_plafond_rotterdam_admissible", age)
            if rotterdam_stale_price_admissible is False:
                return Decision(False, "double_plafond_rotterdam_verrouille", age)
            return Decision(False, "double_plafond_rotterdam_indisponible", age)

        if not recent_nonprincipal_liveness(activity_by_fuel=activity_by_fuel, day=day):
            return Decision(False, "double_plafond_bdr_sans_vivacite_autre_carburant", age)
        if rotterdam_stale_price_admissible is True:
            return Decision(True, "double_plafond_bdr_vivacite_et_rotterdam", age)
        if rotterdam_stale_price_admissible is False:
            return Decision(False, "double_plafond_rotterdam_verrouille", age)
        return Decision(False, "double_plafond_rotterdam_indisponible", age)

    # Single-cap case: every qualifying declaration starts a fresh rolling 45-day
    # support window. There is deliberately no arbitrary J+90 stop in C2/BdR.
    if recent_liveness(
        region_kind=region_kind,
        target_fuel=target_fuel,
        activity_by_fuel=activity_by_fuel,
        day=day,
    ):
        return Decision(True, "bouclier_vivacite_45j_renouvelee", age)
    return Decision(False, "bouclier_sans_vivacite_recente", age)
