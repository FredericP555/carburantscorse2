#!/usr/bin/env python3
"""Assert that duplicated monthly C2 publication constants still match production defaults.

The monthly EPCI thresholds are intentionally independent. The C2 sample guards are not: until
production exports named constants, this validator makes any drift fail closed instead of silently
changing the monthly comparison.
"""
from __future__ import annotations

import inspect

from carburantscorse2.publication import build_gap_series
from scripts import build_monthly_territorial as monthly
from scripts.build_v2_production_candidate import SWITCH_DAY


def main() -> None:
    sig = inspect.signature(build_gap_series)
    prod_corse = sig.parameters["min_corse_stations"].default
    prod_bdr = sig.parameters["min_bdr_stations"].default
    failures: list[str] = []
    if monthly.MIN_C2_CORSE_STATIONS != prod_corse:
        failures.append(f"Corsica guard monthly={monthly.MIN_C2_CORSE_STATIONS}, production={prod_corse}")
    if monthly.MIN_C2_BDR_STATIONS != prod_bdr:
        failures.append(f"BDR guard monthly={monthly.MIN_C2_BDR_STATIONS}, production={prod_bdr}")
    if str(SWITCH_DAY) != "2026-07-23":
        failures.append(f"unexpected production V2 switch date: {SWITCH_DAY}")
    if failures:
        raise RuntimeError("Monthly/C2 production contract drift: " + "; ".join(failures))
    print(
        "Monthly/C2 contract OK: "
        f"sample guards Corse={prod_corse}, BDR={prod_bdr}; V2 switch={SWITCH_DAY}; "
        "EPCI ranking thresholds remain independent"
    )


if __name__ == "__main__":
    main()
