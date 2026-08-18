#!/usr/bin/env python3
"""Published Gazole apparent-margin aggregation for carburantscorse2."""
from __future__ import annotations

import pandas as pd

from carburantscorse2.margins import excise_gazole_eur_l


def build_margin_series(
    state: pd.DataFrame,
    rotterdam_daily: pd.DataFrame,
    *,
    bdr_scope: str = "all",
    min_corse_stations: int = 5,
    min_bdr_stations: int = 10,
) -> list[dict]:
    """Return Monday-week apparent Gazole margins in c€/L.

    The calculation is performed at station-day level, using the 4-decimal HT value of
    the published price profile, then averaged over all eligible station-days in the week.
    This preserves any day-to-day variation in station counts and in Rotterdam values.
    """
    if bdr_scope not in {"all", "network"}:
        raise ValueError("bdr_scope must be all or network")

    prices = state[state["eligible_publication"] & state["fuel"].eq("Gazole")].copy()
    prices["date_key"] = pd.to_datetime(prices["date"]).dt.normalize()
    rot = rotterdam_daily.copy()
    rot["date_key"] = pd.to_datetime(rot["date"]).dt.normalize()
    if "rotterdam_eur_l" not in rot.columns:
        raise ValueError("rotterdam_daily must contain rotterdam_eur_l")
    prices = prices.merge(rot[["date_key", "rotterdam_eur_l"]], on="date_key", how="left")
    if prices["rotterdam_eur_l"].isna().any():
        first = prices.loc[prices["rotterdam_eur_l"].isna(), "date_key"].min()
        raise ValueError(f"Missing Rotterdam value from {first.date()}")

    prices["excise_eur_l"] = [
        excise_gazole_eur_l(dep, d.date())
        for dep, d in zip(prices["department"].astype(str), prices["date_key"])
    ]
    prices["margin_eur_l"] = prices["price_ht"] - prices["excise_eur_l"] - prices["rotterdam_eur_l"]
    prices["period"] = prices["date_key"] - pd.to_timedelta(prices["date_key"].dt.weekday, unit="D")

    corsica = prices[prices["territory"].eq("Corse")]
    bdr_all = prices[prices["territory"].eq("Bouches-du-Rhone")]
    bdr = bdr_all if bdr_scope == "all" else bdr_all[bdr_all["category"].eq("network")]

    cg = corsica.groupby("period").agg(corse=("margin_eur_l", "mean"), n_corse=("station_id", "nunique"))
    bg = bdr.groupby("period").agg(bdr=("margin_eur_l", "mean"), n_bdr_scope=("station_id", "nunique"))
    guard = bdr_all.groupby("period").agg(n_bdr_guard=("station_id", "nunique"))
    merged = cg.join(bg, how="inner").join(guard, how="left")
    merged = merged[(merged["n_corse"] >= min_corse_stations) & (merged["n_bdr_guard"] >= min_bdr_stations)]

    result: list[dict] = []
    for period, row in merged.sort_index().iterrows():
        corse = float(row["corse"]) * 100.0
        bdr_value = float(row["bdr"]) * 100.0
        result.append(
            {
                "date": pd.Timestamp(period).strftime("%Y-%m-%d"),
                "ecart": round(corse - bdr_value, 2),
                "corse": round(corse, 2),
                "bdr": round(bdr_value, 2),
            }
        )
    return result
