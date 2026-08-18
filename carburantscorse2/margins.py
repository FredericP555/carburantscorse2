#!/usr/bin/env python3
"""Gazole apparent distribution-margin helpers for carburantscorse2."""
from __future__ import annotations

from datetime import date
import pandas as pd


def excise_gazole_eur_l(department: str, when: date) -> float:
    if str(department) == "20":
        return 0.5940
    if str(department) == "13":
        return 0.5940 if when.year <= 2024 else 0.6075
    raise ValueError(f"Unsupported department {department}")


def compute_gazole_margin(price_ttc: float, department: str, when: date, rotterdam_eur_l: float) -> float:
    vat = 1.13 if str(department) == "20" else 1.20 if str(department) == "13" else None
    if vat is None:
        raise ValueError(f"Unsupported department {department}")
    price_ht = float(price_ttc) / vat
    return price_ht - excise_gazole_eur_l(department, when) - float(rotterdam_eur_l)


def attach_gazole_margin(daily_prices: pd.DataFrame, rotterdam_daily: pd.DataFrame) -> pd.DataFrame:
    prices = daily_prices[daily_prices["fuel"].eq("Gazole")].copy()
    prices["date_key"] = pd.to_datetime(prices["date"]).dt.date
    rot = rotterdam_daily.copy()
    rot["date_key"] = pd.to_datetime(rot["date"]).dt.date
    merged = prices.merge(rot.drop(columns=["date"], errors="ignore"), on="date_key", how="left")
    merged["excise_eur_l"] = [
        excise_gazole_eur_l(dep, d) for dep, d in zip(merged["department"], merged["date_key"])
    ]
    merged["price_ht"] = merged["price"] / merged["department"].map({"20": 1.13, "13": 1.20})
    merged["margin_apparent_eur_l"] = merged["price_ht"] - merged["excise_eur_l"] - merged["rotterdam_eur_l"]
    return merged
