#!/usr/bin/env python3
"""Prepared Rotterdam calibration helper for C2.

This module never fetches UFIP directly. It only reads CSV files produced by
scripts/fetch_ufip.py. It is inactive until explicitly wired into publication.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping

DEFAULT_OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DEFAULT_DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
VALUE_COLUMN = "rotterdam_eur_l"
DATE_COLUMN = "date"

CALIBRATION_ENTRY_DATE_2026 = date(2026, 4, 8)
R1_OBSERVATION_COUNT = 3

# Empirical C2 candidate calibrations, deliberately territory-specific.
# They are derived from the same UFIP Rotterdam Gazole series:
# - Corse: exit observations 2026-05-29, 2026-06-01, 2026-06-02.
# - BDR Total classique: 2026-05-20, 2026-05-21, 2026-05-22.
CALIBRATION_EXIT_DATES_2026 = {
    "corsica": (date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2)),
    "bdr": (date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22)),
}

@dataclass(frozen=True)
class RotterdamCalibration:
    territory: str
    entry_date: date
    r1: float
    k: float
    r2: float
    r1_source_dates: tuple[date, ...]
    exit_source_dates: tuple[date, ...]


def read_observed_csv(path: str | Path = DEFAULT_OBSERVED_FILE) -> dict[date, float]:
    """Read observed UFIP quotations only; carried calendar values are not accepted here."""
    values: dict[date, float] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {DATE_COLUMN, VALUE_COLUMN}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"UFIP observed CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date = (row.get(DATE_COLUMN) or "").strip()
            raw_value = (row.get(VALUE_COLUMN) or "").strip()
            if not raw_date or not raw_value:
                continue
            values[date.fromisoformat(raw_date[:10])] = float(raw_value)
    if not values:
        raise ValueError("UFIP observed CSV contains no usable Rotterdam Gazole value")
    return dict(sorted(values.items()))


def last_observed_before(
    observations: Mapping[date, float],
    entry_date: date,
    count: int = R1_OBSERVATION_COUNT,
) -> tuple[tuple[date, float], ...]:
    if count <= 0:
        raise ValueError("count must be > 0")
    candidates = [(d, float(v)) for d, v in observations.items() if d < entry_date]
    candidates.sort(key=lambda item: item[0])
    if len(candidates) < count:
        raise ValueError(
            f"Need {count} observed UFIP quotations before {entry_date.isoformat()}, "
            f"found {len(candidates)}"
        )
    return tuple(candidates[-count:])


def compute_r1(
    observations: Mapping[date, float],
    entry_date: date,
    count: int = R1_OBSERVATION_COUNT,
) -> tuple[float, tuple[date, ...]]:
    selected = last_observed_before(observations, entry_date, count)
    return mean(v for _, v in selected), tuple(d for d, _ in selected)


def mean_on_dates(
    observations: Mapping[date, float],
    dates: Iterable[date],
) -> tuple[float, tuple[date, ...]]:
    requested = tuple(dates)
    missing = tuple(d for d in requested if d not in observations)
    if missing:
        raise ValueError(
            "Missing observed UFIP quotations for calibration dates: "
            + ", ".join(d.isoformat() for d in missing)
        )
    return mean(float(observations[d]) for d in requested), requested


def calibrate_2026(
    territory: str,
    observed_file: str | Path = DEFAULT_OBSERVED_FILE,
) -> RotterdamCalibration:
    """Recompute the C2 candidate k from the UFIP automation output."""
    if territory not in CALIBRATION_EXIT_DATES_2026:
        raise ValueError("territory must be 'corsica' or 'bdr'")
    observations = read_observed_csv(observed_file)
    r1, r1_dates = compute_r1(observations, CALIBRATION_ENTRY_DATE_2026)
    exit_mean, exit_dates = mean_on_dates(
        observations, CALIBRATION_EXIT_DATES_2026[territory]
    )
    k = exit_mean / r1
    return RotterdamCalibration(
        territory=territory,
        entry_date=CALIBRATION_ENTRY_DATE_2026,
        r1=r1,
        k=k,
        r2=k * r1,
        r1_source_dates=r1_dates,
        exit_source_dates=exit_dates,
    )


def read_daily_value(
    day: date,
    path: str | Path = DEFAULT_DAILY_FILE,
) -> float | None:
    """Read one day from the forward-filled UFIP daily file produced by automation."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {DATE_COLUMN, VALUE_COLUMN}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"UFIP daily CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date = (row.get(DATE_COLUMN) or "").strip()
            if raw_date and date.fromisoformat(raw_date[:10]) == day:
                raw_value = (row.get(VALUE_COLUMN) or "").strip()
                return None if not raw_value else float(raw_value)
    return None


def threshold_for(
    territory: str,
    observed_file: str | Path = DEFAULT_OBSERVED_FILE,
) -> float:
    """Return R2 for the requested C2 territory from the UFIP-produced observed file."""
    return calibrate_2026(territory, observed_file).r2
