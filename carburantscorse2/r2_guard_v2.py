#!/usr/bin/env python3
"""Prepared R2 guard derived from target declaration + current shield phase."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from carburantscorse2 import rotterdam_calibration_v2 as rotterdam

NORMAL_MAX_AGE_DAYS = 45


def stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    territory: str,
    *,
    phase_started_on: date | None,
    observed_file: str | Path = rotterdam.DEFAULT_OBSERVED_FILE,
    daily_file: str | Path = rotterdam.DEFAULT_DAILY_FILE,
    shared_meta_file: str | Path = rotterdam.DEFAULT_SHARED_META_FILE,
) -> bool:
    """Return the persistent R2 verdict for the current effective-shield phase.

    The first stale day is always declaration date + 45 calendar days. R2 itself
    is recalculated for each new effective-shield cap phase from the three last
    actually observed Rotterdam quotations before that phase starts, using the
    fixed historical territorial coefficient k.
    """
    if territory not in {"corsica", "bdr"}:
        raise ValueError("territory must be 'corsica' or 'bdr'")
    if last_declared_at is None or phase_started_on is None:
        return False
    declared_on = last_declared_at.date()
    if declared_on > day or phase_started_on > day:
        return False
    stale_start = declared_on + timedelta(days=NORMAL_MAX_AGE_DAYS)
    if day < stale_start:
        return True
    if stale_start < phase_started_on:
        return False
    return rotterdam.admissible_since(
        stale_start,
        day,
        territory,
        phase_started_on=phase_started_on,
        observed_file=observed_file,
        daily_file=daily_file,
        shared_meta_file=shared_meta_file,
    )
