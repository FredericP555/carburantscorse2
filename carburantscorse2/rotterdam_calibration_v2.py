#!/usr/bin/env python3
"""Prepared Rotterdam calibration helper for C2.

C2 never queries UFIP in the prepared architecture. It downloads the Rotterdam
assets already published by C1. The Corsica calibration is consumed directly
from C1 shared metadata; only the BDR-specific candidate k is derived locally
from the shared observed CSV.

R2 is an admissibility threshold for stale station prices in the double-cap
case. It never defines whether the TotalEnergies shield itself is effective.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping

DEFAULT_OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DEFAULT_DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
DEFAULT_SHARED_META_FILE = Path("outputs/ufip/c1_shared_meta.json")
VALUE_COLUMN = "rotterdam_eur_l"
DATE_COLUMN = "date"

CALIBRATION_ENTRY_DATE_2026 = date(2026, 4, 8)
R1_OBSERVATION_COUNT = 3
BDR_EXIT_DATES_2026 = (date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22))


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


def corsica_from_shared_metadata(
    meta_file: str | Path = DEFAULT_SHARED_META_FILE,
) -> RotterdamCalibration:
    """Consume the canonical Corsica calibration already produced by C1."""
    payload = json.loads(Path(meta_file).read_text(encoding="utf-8"))
    rotterdam = payload.get("rotterdam")
    calibration = rotterdam.get("corsica_calibration") if isinstance(rotterdam, dict) else None
    if not isinstance(calibration, dict):
        raise ValueError("C1 shared metadata has no Corsica Rotterdam calibration")
    if calibration.get("territory") != "corsica":
        raise ValueError("C1 shared Rotterdam calibration territory is not corsica")
    try:
        return RotterdamCalibration(
            territory="corsica",
            entry_date=date.fromisoformat(str(calibration["entry_date"])),
            r1=float(calibration["r1"]),
            k=float(calibration["k"]),
            r2=float(calibration["r2"]),
            r1_source_dates=tuple(date.fromisoformat(str(d)) for d in calibration["r1_source_dates"]),
            exit_source_dates=tuple(date.fromisoformat(str(d)) for d in calibration["exit_source_dates"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid C1 shared Corsica Rotterdam calibration") from exc


def calibrate_2026(
    territory: str,
    observed_file: str | Path = DEFAULT_OBSERVED_FILE,
    shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE,
) -> RotterdamCalibration:
    """Return C1's canonical Corse calibration or derive the BDR-specific candidate."""
    if territory == "corsica":
        return corsica_from_shared_metadata(shared_meta_file)
    if territory != "bdr":
        raise ValueError("territory must be 'corsica' or 'bdr'")

    observations = read_observed_csv(observed_file)
    r1, r1_dates = compute_r1(observations, CALIBRATION_ENTRY_DATE_2026)
    exit_mean, exit_dates = mean_on_dates(observations, BDR_EXIT_DATES_2026)
    k = exit_mean / r1
    return RotterdamCalibration(
        territory="bdr",
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
    """Read one day from the C1-published forward-filled Rotterdam daily file."""
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
    shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE,
) -> float:
    """Return R2 using C1 metadata for Corse and the shared CSV for BDR."""
    return calibrate_2026(territory, observed_file, shared_meta_file).r2


def constraining_on(
    day: date,
    territory: str,
    *,
    observed_file: str | Path = DEFAULT_OBSERVED_FILE,
    daily_file: str | Path = DEFAULT_DAILY_FILE,
    shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE,
) -> bool:
    """Return whether Rotterdam is on the admissible side of territory R2.

    Agreed runtime rule: Rotterdam >= R2 means the stale double-cap price may
    remain admissible subject to the other guards; Rotterdam < R2 excludes it.
    Missing data fails closed by raising. This does not alter shield-effective
    status, which is determined independently by C1's shield detector.
    """
    if territory not in {"corsica", "bdr"}:
        raise ValueError("territory must be 'corsica' or 'bdr'")
    value = read_daily_value(day, daily_file)
    if value is None:
        raise ValueError(f"Missing Rotterdam daily value for {day.isoformat()}")
    r2 = threshold_for(territory, observed_file, shared_meta_file)
    return float(value) >= float(r2)
