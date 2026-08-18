#!/usr/bin/env python3
"""Recovered 14-Jun-2026 reliability profile for carburantscorse2.

This file follows the executable reference scripts saved in the user's methodology
archive, not the older prose methodology where thresholds differ. The mismatch is
kept explicit in docs/methodology-differences.md and will be resolved by regression
against the published dashboard before production is changed.
"""
from __future__ import annotations

import pandas as pd

PRICE_MIN = 1.10
PRICE_MAX = 3.00
GAP_THRESHOLDS = {"13": 30, "20": 90}
GAP_THRESHOLDS_BY_DEPT_FUEL = {("13", "SP95"): 21}
INACTIVE_THRESHOLDS = {"13": 60, "20": 180}


def territory_label(department: str) -> str:
    return "Corse" if str(department) == "20" else "Bouches-du-Rhone"


def _bool_series(value: pd.Series) -> pd.Series:
    if value.dtype == bool:
        return value
    return value.astype(str).str.lower().isin({"true", "1", "yes"})


def prepare_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common observations to the columns used by the c2 profile."""
    out = df.copy()
    out["station_id"] = out["station_id"].astype(str)
    out["department"] = out["department"].astype(str)
    out["fuel"] = out["fuel"].astype(str)
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    if "is_motorway" not in out.columns:
        pop = out["pop"] if "pop" in out.columns else pd.Series("", index=out.index)
        out["is_motorway"] = pop.astype(str).eq("A")
    else:
        out["is_motorway"] = _bool_series(out["is_motorway"])
    out["price_aberrant"] = out["price"].lt(PRICE_MIN) | out["price"].gt(PRICE_MAX) | out["price"].isna()
    out["territory"] = out["department"].map(territory_label)
    return out


def filter_project_perimeter(df: pd.DataFrame) -> pd.DataFrame:
    """Apply c2 perimeter but no forward-fill/reliability state yet."""
    out = prepare_observations(df)
    out = out[out["department"].isin(["13", "20"])].copy()
    out = out[~out["is_motorway"]].copy()
    out = out[out["fuel"].isin(["Gazole", "SP95", "E10"])].copy()
    out = out[~((out["department"] == "20") & (out["fuel"] == "E10"))].copy()
    return out


def deduplicate_daily(df: pd.DataFrame) -> pd.DataFrame:
    out = filter_project_perimeter(df)
    return (
        out.sort_values(["station_id", "fuel", "date", "timestamp"])
        .drop_duplicates(["station_id", "fuel", "date"], keep="last")
        .reset_index(drop=True)
    )


def build_daily_series(daily_observations: pd.DataFrame, *, global_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Reproduce the recovered June-2026 c2 daily-state algorithm."""
    if daily_observations.empty:
        return pd.DataFrame()
    daily = daily_observations.copy()
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    daily["timestamp"] = pd.to_datetime(daily["timestamp"])
    global_end = pd.Timestamp(global_end).normalize() if global_end is not None else daily["date"].max()
    pieces = []

    metadata_cols = [
        "station_id", "department", "territory", "cp", "city", "address", "pop",
        "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "price",
        "timestamp", "price_aberrant",
    ]
    metadata_cols = [c for c in metadata_cols if c in daily.columns]

    for (_station, _fuel), group in daily.groupby(["station_id", "fuel"], sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        start = group["date"].min()
        dates = pd.date_range(start, global_end, freq="D")
        obs = group[metadata_cols + ["date"]].rename(columns={"timestamp": "source_timestamp"})
        frame = pd.DataFrame({"date": dates}).merge(obs, on="date", how="left")
        fill_cols = [c for c in metadata_cols if c != "timestamp"]
        if "source_timestamp" not in fill_cols:
            fill_cols.append("source_timestamp")
        with pd.option_context("future.no_silent_downcasting", True):
            filled = frame[fill_cols].ffill()
        frame[fill_cols] = filled.infer_objects(copy=False)

        real_dates = set(group["date"])
        frame["real_observation"] = frame["date"].isin(real_dates)
        frame["source_observation_date"] = frame["date"].where(frame["real_observation"]).ffill()
        frame["days_since_observation"] = (frame["date"] - frame["source_observation_date"]).dt.days

        department = str(group.loc[0, "department"])
        fuel = str(group.loc[0, "fuel"])
        gap_threshold = GAP_THRESHOLDS_BY_DEPT_FUEL.get((department, fuel), GAP_THRESHOLDS[department])
        inactive_threshold = INACTIVE_THRESHOLDS[department]
        frame["gap_threshold_days"] = gap_threshold
        frame["inactive_threshold_days"] = inactive_threshold
        frame["gap_suspect"] = frame["days_since_observation"].gt(gap_threshold)

        last_date = group["date"].max()
        frame["station_inactive"] = frame["date"].gt(last_date) & frame["days_since_observation"].gt(inactive_threshold)

        next_dates = group[["date"]].copy()
        next_dates["source_observation_date"] = next_dates["date"]
        next_dates["next_observation_date"] = next_dates["date"].shift(-1)
        frame = frame.merge(next_dates[["source_observation_date", "next_observation_date"]], on="source_observation_date", how="left")
        frame["gap_days_to_next_observation"] = (frame["next_observation_date"] - frame["source_observation_date"]).dt.days
        frame = frame.drop(columns=["next_observation_date"])
        pieces.append(frame)

    out = pd.concat(pieces, ignore_index=True)
    out["eligible_price_average"] = ~(out["price_aberrant"] | out["gap_suspect"] | out["station_inactive"])
    reasons = pd.Series("", index=out.index, dtype="object")
    reasons = reasons.mask(out["price_aberrant"], reasons + "prix_aberrant;")
    reasons = reasons.mask(out["gap_suspect"], reasons + "gap_suspect;")
    reasons = reasons.mask(out["station_inactive"], reasons + "station_inactive;")
    out["exclusion_reasons"] = reasons.str.rstrip(";")
    return out


def add_tax_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["vat_rate"] = out["department"].map({"20": 0.13, "13": 0.20})
    out["price_ht"] = out["price"] / (1.0 + out["vat_rate"])
    return out
