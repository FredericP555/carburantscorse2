#!/usr/bin/env python3
"""Prepared Rotterdam calibration helper for C2.

C2 never queries UFIP in the prepared architecture. It downloads the Rotterdam
assets already published by C1.

The 2026 reference episode calibrates the territorial coefficients ``k`` only.
For every effective-shield cap phase, R1 is recomputed from the three last
actually observed Rotterdam quotations before that phase starts, then
``R2 = k * R1``. R2 never starts or ends the TotalEnergies shield.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping

DEFAULT_OBSERVED_FILE = Path("outputs/ufip/rotterdam_gazole_observed.csv")
DEFAULT_DAILY_FILE = Path("outputs/ufip/rotterdam_gazole_daily.csv")
DEFAULT_SHARED_META_FILE = Path("outputs/ufip/c1_shared_meta.json")
VALUE_COLUMN = "rotterdam_eur_l"
DATE_COLUMN = "date"
BASELINE_ENTRY_DATE_2026 = date(2026, 4, 8)
BASELINE_R1_SOURCE_DATES_2026 = (date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7))
BDR_BASELINE_EXIT_DATES_2026 = (date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22))
CORSE_BASELINE_EXIT_DATES_2026 = (date(2026, 5, 29), date(2026, 6, 1), date(2026, 6, 2))
R1_OBSERVATION_COUNT = 3
CALIBRATION_ABS_TOLERANCE = 1e-9
CALIBRATION_ENTRY_DATE_2026 = BASELINE_ENTRY_DATE_2026
R1_SOURCE_DATES_2026 = BASELINE_R1_SOURCE_DATES_2026
BDR_EXIT_DATES_2026 = BDR_BASELINE_EXIT_DATES_2026
CORSE_EXIT_DATES_2026 = CORSE_BASELINE_EXIT_DATES_2026

@dataclass(frozen=True)
class RotterdamCalibration:
    territory: str
    entry_date: date
    r1: float
    k: float
    r2: float
    r1_source_dates: tuple[date, ...]
    exit_source_dates: tuple[date, ...]


def _finite_float(raw, *, context: str) -> float:
    try: value=float(raw)
    except (TypeError,ValueError) as exc: raise ValueError(f"Invalid Rotterdam value in {context}: {raw!r}") from exc
    if not math.isfinite(value): raise ValueError(f"Non-finite Rotterdam value in {context}: {raw!r}")
    return value

def read_observed_csv(path: str | Path = DEFAULT_OBSERVED_FILE) -> dict[date,float]:
    values={}
    with Path(path).open("r",encoding="utf-8-sig",newline="") as fh:
        reader=csv.DictReader(fh); required={DATE_COLUMN,VALUE_COLUMN}; missing=required-set(reader.fieldnames or [])
        if missing: raise ValueError(f"UFIP observed CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date=(row.get(DATE_COLUMN) or "").strip(); raw_value=(row.get(VALUE_COLUMN) or "").strip()
            if raw_date and raw_value:
                day=date.fromisoformat(raw_date[:10]); values[day]=_finite_float(raw_value,context=f"observed {day}")
    if not values: raise ValueError("UFIP observed CSV contains no usable Rotterdam Gazole value")
    return dict(sorted(values.items()))

def mean_on_dates(observations: Mapping[date,float], dates: Iterable[date]) -> tuple[float,tuple[date,...]]:
    requested=tuple(dates); missing=tuple(d for d in requested if d not in observations)
    if missing: raise ValueError("Missing observed UFIP quotations for calibration dates: "+", ".join(d.isoformat() for d in missing))
    return mean(_finite_float(observations[d],context=f"calibration {d}") for d in requested), requested

def last_observed_before(observations: Mapping[date,float], entry_date: date, count: int = R1_OBSERVATION_COUNT) -> tuple[tuple[date,float],...]:
    if count <= 0: raise ValueError("count must be > 0")
    rows=sorted((d,_finite_float(v,context=f"observed {d}")) for d,v in observations.items() if d < entry_date)
    if len(rows)<count: raise ValueError(f"Need {count} observed UFIP quotations before {entry_date}, found {len(rows)}")
    return tuple(rows[-count:])
def _validate_corsica_calibration(calibration: dict) -> RotterdamCalibration:
    if calibration.get("territory") != "corsica": raise ValueError("C1 shared Rotterdam calibration territory is not corsica")
    try:
        entry_date=date.fromisoformat(str(calibration["entry_date"])); r1=_finite_float(calibration["r1"],context="shared Corsica baseline r1"); k=_finite_float(calibration["k"],context="shared Corsica k"); r2=_finite_float(calibration["r2"],context="shared Corsica baseline r2"); r1_dates=tuple(date.fromisoformat(str(d)) for d in calibration["r1_source_dates"]); exit_dates=tuple(date.fromisoformat(str(d)) for d in calibration["exit_source_dates"])
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("Invalid C1 shared Corsica Rotterdam calibration") from exc
    if entry_date != BASELINE_ENTRY_DATE_2026: raise ValueError("Unexpected C1 Corsica baseline calibration entry date")
    if r1_dates != BASELINE_R1_SOURCE_DATES_2026: raise ValueError("Unexpected C1 Corsica baseline R1 source dates")
    if exit_dates != CORSE_BASELINE_EXIT_DATES_2026: raise ValueError("Unexpected C1 Corsica baseline exit source dates")
    if r1<=0 or k<=0 or r2<=0: raise ValueError("C1 Corsica calibration values must be positive")
    if not math.isclose(r1*k,r2,rel_tol=0.0,abs_tol=CALIBRATION_ABS_TOLERANCE): raise ValueError("C1 Corsica calibration invariant r1*k=r2 is broken")
    return RotterdamCalibration("corsica",entry_date,r1,k,r2,r1_dates,exit_dates)
def corsica_from_shared_metadata(meta_file: str | Path = DEFAULT_SHARED_META_FILE) -> RotterdamCalibration:
    payload=json.loads(Path(meta_file).read_text(encoding="utf-8")); rotterdam=payload.get("rotterdam"); calibration=rotterdam.get("corsica_calibration") if isinstance(rotterdam,dict) else None
    if not isinstance(calibration,dict): raise ValueError("C1 shared metadata has no Corsica Rotterdam calibration")
    return _validate_corsica_calibration(calibration)
def calibrate_2026(territory: str, observed_file: str | Path = DEFAULT_OBSERVED_FILE, shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE) -> RotterdamCalibration:
    if territory=="corsica": return corsica_from_shared_metadata(shared_meta_file)
    if territory!="bdr": raise ValueError("territory must be 'corsica' or 'bdr'")
    observations=read_observed_csv(observed_file); r1,r1_dates=mean_on_dates(observations,BASELINE_R1_SOURCE_DATES_2026); exit_mean,exit_dates=mean_on_dates(observations,BDR_BASELINE_EXIT_DATES_2026); k=exit_mean/r1
    return RotterdamCalibration("bdr",BASELINE_ENTRY_DATE_2026,r1,k,exit_mean,r1_dates,exit_dates)
def calibrate_phase(territory: str, phase_started_on: date, observed_file: str | Path = DEFAULT_OBSERVED_FILE, shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE) -> RotterdamCalibration:
    baseline=calibrate_2026(territory,observed_file,shared_meta_file); observations=read_observed_csv(observed_file); r1_rows=last_observed_before(observations,phase_started_on); r1=mean(v for _,v in r1_rows)
    return RotterdamCalibration(territory,phase_started_on,r1,baseline.k,baseline.k*r1,tuple(d for d,_ in r1_rows),baseline.exit_source_dates)
def read_daily_values(path: str | Path = DEFAULT_DAILY_FILE) -> dict[date,float]:
    values={}
    with Path(path).open("r",encoding="utf-8-sig",newline="") as fh:
        reader=csv.DictReader(fh); required={DATE_COLUMN,VALUE_COLUMN}; missing=required-set(reader.fieldnames or [])
        if missing: raise ValueError(f"UFIP daily CSV missing columns: {sorted(missing)}")
        for row in reader:
            raw_date=(row.get(DATE_COLUMN) or "").strip(); raw_value=(row.get(VALUE_COLUMN) or "").strip()
            if raw_date and raw_value: values[date.fromisoformat(raw_date[:10])]=_finite_float(raw_value,context=f"daily {raw_date[:10]}")
    return values
def threshold_for(territory: str, phase_started_on: date, observed_file: str | Path = DEFAULT_OBSERVED_FILE, shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE) -> float:
    return calibrate_phase(territory,phase_started_on,observed_file,shared_meta_file).r2
def admissible_since(start_day: date,end_day: date,territory: str,*,phase_started_on: date,observed_file: str | Path = DEFAULT_OBSERVED_FILE,daily_file: str | Path = DEFAULT_DAILY_FILE,shared_meta_file: str | Path = DEFAULT_SHARED_META_FILE) -> bool:
    if territory not in {"corsica","bdr"}: raise ValueError("territory must be 'corsica' or 'bdr'")
    if end_day < start_day: raise ValueError("end_day must be >= start_day")
    if phase_started_on > start_day: raise ValueError("stale-price window starts before current shield phase")
    values=read_daily_values(daily_file); r2=threshold_for(territory,phase_started_on,observed_file,shared_meta_file); d=start_day
    while d<=end_day:
        if d not in values: raise ValueError(f"Missing Rotterdam daily value for {d.isoformat()}")
        if values[d] < r2: return False
        d += timedelta(days=1)
    return True
