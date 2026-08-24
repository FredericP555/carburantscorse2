#!/usr/bin/env python3
"""Performance wrapper for the real-data V2 dry-run.

The prepared policy helpers intentionally favor explicit validation over caching. A live
station/day audit may call the same phase and R2 questions thousands of times, so this
wrapper memoizes them without changing any verdict. Production code is untouched.
"""
from __future__ import annotations

from datetime import date, datetime

from carburantscorse2 import r2_guard_v2, shield_phase_v2

_original_phase_for_day = shield_phase_v2.phase_for_day
_original_double_cap_period_for_day = shield_phase_v2.double_cap_period_for_day
_original_stale_price_admissible = r2_guard_v2.stale_price_admissible

_phase_cache = {}
_double_cache = {}
_r2_cache = {}


def _cached_phase_for_day(metadata, fuel: str, day: date):
    key = (id(metadata), fuel, day)
    if key not in _phase_cache:
        _phase_cache[key] = _original_phase_for_day(metadata, fuel, day)
    return _phase_cache[key]


def _cached_double_cap_period_for_day(metadata, day: date):
    key = (id(metadata), day)
    if key not in _double_cache:
        _double_cache[key] = _original_double_cap_period_for_day(metadata, day)
    return _double_cache[key]


def _cached_stale_price_admissible(
    last_declared_at: datetime | None,
    day: date,
    territory: str,
    *,
    bouclier_metadata,
    observed_file=r2_guard_v2.rotterdam.DEFAULT_OBSERVED_FILE,
    daily_file=r2_guard_v2.rotterdam.DEFAULT_DAILY_FILE,
    shared_meta_file=r2_guard_v2.rotterdam.DEFAULT_SHARED_META_FILE,
):
    key = (
        last_declared_at,
        day,
        territory,
        str(observed_file),
        str(daily_file),
        str(shared_meta_file),
    )
    if key not in _r2_cache:
        try:
            value = _original_stale_price_admissible(
                last_declared_at,
                day,
                territory,
                bouclier_metadata=bouclier_metadata,
                observed_file=observed_file,
                daily_file=daily_file,
                shared_meta_file=shared_meta_file,
            )
            _r2_cache[key] = (True, bool(value))
        except Exception as exc:
            _r2_cache[key] = (False, (type(exc), str(exc)))
    ok, payload = _r2_cache[key]
    if ok:
        return payload
    exc_type, message = payload
    raise exc_type(message)


shield_phase_v2.phase_for_day = _cached_phase_for_day
shield_phase_v2.double_cap_period_for_day = _cached_double_cap_period_for_day
r2_guard_v2.stale_price_admissible = _cached_stale_price_admissible

from scripts.dry_run_v2_candidate import main


if __name__ == "__main__":
    main()
