#!/usr/bin/env python3
"""Prepared R2 guard derived from declaration + current double-cap period."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping

from carburantscorse2 import rotterdam_calibration_v2 as rotterdam
from carburantscorse2 import shield_phase_v2 as shield_phase

NORMAL_MAX_AGE_DAYS = 45


def stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    territory: str,
    *,
    bouclier_metadata: Mapping,
    observed_file: str | Path = rotterdam.DEFAULT_OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DEFAULT_DAILY_FILE,
    shared_meta_file: str | Path = rotterdam.DEFAULT_SHARED_META_FILE,
) -> bool:
    """Return the persistent R2 verdict for the current double-cap period.

    The period anchor is derived internally from the overlap of the Gazole and
    SP95 effective phases. R2 is then recalculated from the three last actually
    observed Rotterdam quotations before that overlap begins, with the fixed
    territorial coefficient k.
    """
    if territory not in {"corsica", "bdr"}:
        raise ValueError("territory must be 'corsica' or 'bdr'")
    if last_declared_at is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day:
        return False

    period = shield_phase.double_cap_period_for_day(bouclier_metadata, day)
    if period is None:
        return False

    stale_start = declared_on + timedelta(days=NORMAL_MAX_AGE_DAYS)
    if day < stale_start:
        return True
    if stale_start < period.started_on:
        return False
    return rotterdam.admissible_since(
        stale_start,
        day,
        territory,
        phase_started_on=period.started_on,
        observed_file=observed_file,
        daily_file=daily_file,
        shared_meta_file=shared_meta_file,
    )
