#!/usr/bin/env python3
"""Publication profile that reproduces the current carburantscorse2 dashboard in 2026.

This is deliberately distinct from ``carburantscorse2.method``. The latter encodes the
more conservative 14-Jun-2026 reconstructed research method. This module encodes the
method actually evidenced by the dashboard published through 6 Jun 2026, so future
updates can be appended without silently rewriting its historical series.

Recovered publication behaviour for current-period prices:
- Corse/BdR, Gazole + SP95, BDR E10 as secondary reference;
- motorway stations excluded;
- last declaration per station/fuel/day wins;
- forward-fill between declarations;
- if an *internal* gap is longer than the territory threshold, every carried day
  strictly between the two declarations is excluded (not merely days after the threshold);
- after a station's final declaration, it becomes inactive only after the threshold;
- threshold: 30 days BDR, 150 days Corse;
- HT station-day value is rounded to 4 decimals before aggregation (needed for exact
  reproduction of the published 2026 values);
- minimum published sample: 5 Corsica stations and 10 BDR stations;
- weekly values are station-day means over Monday-Sunday weeks, not means of daily gaps.

Historical 2022 publication also contains manually corrected aberrant values and
brand-specific discount neutralisation. Those historical values stay frozen; this module
is intended for exact continuation of the current-period (2026+) publication profile.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

PRICE_MIN = 1.10
PRICE_MAX = 3.00
GAP_THRESHOLDS = {"13": 30, "20": 150}
VAT_DIVISOR = {"13": 1.20, "20": 1.13}
FUELS = {"Gazole", "SP95", "E10"}


def load_bdr_categories(path: str | Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype={"station_id": str})
    return dict(zip(df["station_id"].astype(str), df["category"].astype(str)))


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin({"1", "true", "yes"})


def prepare_observations(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    out["station_id"] = out["station_id"].astype(str)
    out["department"] = out["department"].astype(str)
    out["fuel"] = out["fuel"].astype(str)
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    if "is_motorway" in out.columns:
        out["is_motorway"] = _as_bool(out["is_motorway"])
    else:
        out["is_motorway"] = out.get("pop", "").astype(str).eq("A")
    out = out[out["department"].isin(["13", "20"])].copy()
    out = out[~out["is_motorway"]].copy()
    out = out[out["fuel"].isin(FUELS)].copy()
    out = out[~((out["department"] == "20") & (out["fuel"] == "E10"))].copy()
    out["price_aberrant"] = out["price"].isna() | out["price"].lt(PRICE_MIN) | out["price"].gt(PRICE_MAX)
    return out


def deduplicate_daily(observations: pd.DataFrame) -> pd.DataFrame:
    out = prepare_observations(observations)
    return (
        out.sort_values(["station_id", "fuel", "date", "timestamp"])
        .drop_duplicates(["station_id", "fuel", "date"], keep="last")
        .reset_index(drop=True)
    )


def build_publication_state(
    daily_observations: pd.DataFrame,
    *,
    global_end: pd.Timestamp,
    bdr_categories: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Expand station observations to the daily state used for publication.

    An out-of-band price is *not* auto-corrected. It remains flagged and is excluded
    until the next declaration. Historical manual corrections stay in the frozen legacy
    history rather than being guessed by an automated job.
    """
    daily = deduplicate_daily(daily_observations)
    if daily.empty:
        return pd.DataFrame()
    global_end = pd.Timestamp(global_end).normalize()
    daily = daily[daily["date"] <= global_end].copy()
    pieces: list[pd.DataFrame] = []

    keep = [
        c for c in [
            "station_id", "department", "cp", "city", "address", "pop",
            "latitude", "longitude", "fuel_id", "fuel", "price", "timestamp",
            "price_aberrant",
        ] if c in daily.columns
    ]

    for (_station, _fuel), group in daily.groupby(["station_id", "fuel"], sort=False):
        group = group.sort_values("date").reset_index(drop=True)
        if group.empty:
            continue
        start = group["date"].min()
        dates = pd.date_range(start, global_end, freq="D")
        observed = group[keep + ["date"]].rename(columns={"timestamp": "source_timestamp"})
        frame = pd.DataFrame({"date": dates}).merge(observed, on="date", how="left")

        fill_cols = [c for c in keep if c != "timestamp"]
        if "source_timestamp" not in fill_cols:
            fill_cols.append("source_timestamp")
        with pd.option_context("future.no_silent_downcasting", True):
            frame[fill_cols] = frame[fill_cols].ffill().infer_objects(copy=False)

        department = str(group.loc[0, "department"])
        threshold = GAP_THRESHOLDS[department]
        real_dates = list(group["date"])
        frame["real_observation"] = frame["date"].isin(set(real_dates))
        frame["gap_suspect"] = False

        # Published legacy behaviour: once a bounded gap is deemed too long, all
        # forward-filled days inside that bounded gap are suspect.
        for previous_date, next_date in zip(real_dates[:-1], real_dates[1:]):
            if (next_date - previous_date).days > threshold:
                mask = (frame["date"] > previous_date) & (frame["date"] < next_date)
                frame.loc[mask, "gap_suspect"] = True

        last_date = real_dates[-1]
        frame["station_inactive"] = frame["date"] > (last_date + pd.Timedelta(days=threshold))
        frame["eligible_publication"] = ~(
            frame["price_aberrant"].fillna(True).astype(bool)
            | frame["gap_suspect"]
            | frame["station_inactive"]
        )
        frame["territory"] = "Corse" if department == "20" else "Bouches-du-Rhone"
        frame["category"] = "network" if department == "20" else frame["station_id"].map(bdr_categories or {}).fillna("unknown")
        frame["price_ht"] = (frame["price"] / VAT_DIVISOR[department]).round(4)
        pieces.append(frame)

    return pd.concat(pieces, ignore_index=True)


def _periodize(df: pd.DataFrame, granularity: str) -> pd.DataFrame:
    out = df.copy()
    if granularity == "daily":
        out["period"] = out["date"]
    elif granularity == "weekly":
        out["period"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    else:
        raise ValueError("granularity must be daily or weekly")
    return out


def build_gap_series(
    state: pd.DataFrame,
    *,
    corsica_fuel: str,
    bdr_fuel: str | None = None,
    bdr_scope: str = "all",
    granularity: str = "daily",
    min_corse_stations: int = 5,
    min_bdr_stations: int = 10,
    include_levels: bool = False,
) -> list[dict]:
    """Build one published gap series.

    ``bdr_scope='network'`` uses the frozen published station-category registry.
    Eligibility for the historical network view follows the published implementation:
    the 10-station guard is checked on the corresponding all-BDR reference sample,
    before the network-only mean is calculated.
    """
    bdr_fuel = bdr_fuel or corsica_fuel
    reliable = state[state["eligible_publication"]].copy()
    corsica = reliable[(reliable["territory"] == "Corse") & (reliable["fuel"] == corsica_fuel)].copy()
    bdr_all = reliable[(reliable["territory"] == "Bouches-du-Rhone") & (reliable["fuel"] == bdr_fuel)].copy()
    bdr = bdr_all if bdr_scope == "all" else bdr_all[bdr_all["category"] == "network"].copy()
    if bdr_scope not in {"all", "network"}:
        raise ValueError("bdr_scope must be all or network")

    corsica = _periodize(corsica, granularity)
    bdr = _periodize(bdr, granularity)
    bdr_all = _periodize(bdr_all, granularity)

    cg = corsica.groupby("period").agg(corse=("price_ht", "mean"), n_corse=("station_id", "nunique"))
    bg = bdr.groupby("period").agg(bdr=("price_ht", "mean"), n_bdr_scope=("station_id", "nunique"))
    guard = bdr_all.groupby("period").agg(n_bdr_guard=("station_id", "nunique"))
    merged = cg.join(bg, how="inner").join(guard, how="left")
    merged = merged[(merged["n_corse"] >= min_corse_stations) & (merged["n_bdr_guard"] >= min_bdr_stations)]

    result: list[dict] = []
    for period, row in merged.sort_index().iterrows():
        item = {
            "date": pd.Timestamp(period).strftime("%Y-%m-%d"),
            "ecart": round((float(row["corse"]) - float(row["bdr"])) * 100.0, 2),
        }
        if include_levels:
            item["corse"] = round(float(row["corse"]), 4)
            item["bdr"] = round(float(row["bdr"]), 4)
        result.append(item)
    return result


def unknown_recent_bdr_stations(state: pd.DataFrame, *, since: pd.Timestamp) -> list[str]:
    recent = state[
        (state["territory"] == "Bouches-du-Rhone")
        & (state["date"] >= pd.Timestamp(since))
        & state["eligible_publication"]
        & state["category"].eq("unknown")
    ]
    return sorted(recent["station_id"].astype(str).unique().tolist())
