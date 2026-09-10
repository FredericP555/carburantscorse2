#!/usr/bin/env python3
"""Build an isolated monthly territorial dataset for the A4C prototype.

This script is intentionally NOT wired into the weekly C2 workflow. It reads the
existing geography registry and the official annual fuel-price stock, reuses C2's
publication-state reliability rules, and writes a standalone JSON file.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from a4c_common.official_prices import download_annual_zip, iter_observations_from_zip
from carburantscorse2.publication import build_publication_state

ROOT = Path(__file__).resolve().parents[1]
FUELS = ("Gazole", "SP95")
MIN_RANK_STATIONS = 3
MIN_RANK_DAY_RATIO = 0.80
MIN_RANK_COVERAGE = 0.80


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True, help="Complete month to build, YYYY-MM")
    p.add_argument(
        "--geography",
        default="config/corse_station_geography_2026.csv",
        help="Station geography registry",
    )
    p.add_argument("--output", help="Output JSON path")
    return p.parse_args()


def month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    try:
        year, mon = (int(v) for v in month.split("-"))
        last = calendar.monthrange(year, mon)[1]
    except Exception as exc:
        raise SystemExit("--month must be formatted YYYY-MM") from exc
    return pd.Timestamp(year=year, month=mon, day=1), pd.Timestamp(year=year, month=mon, day=last)


def previous_month_bounds(start: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    previous_end = start - pd.Timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    return previous_start.normalize(), previous_end.normalize()


def load_geography(path: Path) -> pd.DataFrame:
    geo = pd.read_csv(path, dtype=str).fillna("")
    required = {
        "station_id",
        "localite",
        "commune",
        "epci_siren",
        "epci_nom",
        "source_epci",
        "date_verification",
    }
    missing = required.difference(geo.columns)
    if missing:
        raise RuntimeError(f"Geography file missing columns: {sorted(missing)}")
    if geo["station_id"].duplicated().any():
        dupes = sorted(geo.loc[geo["station_id"].duplicated(keep=False), "station_id"].unique())
        raise RuntimeError(f"Duplicate station_id in geography file: {dupes[:10]}")
    if (geo["epci_siren"].str.strip() == "").any() or (geo["epci_nom"].str.strip() == "").any():
        raise RuntimeError("Every geography row must have epci_siren and epci_nom")
    return geo


def load_observations(years: Iterable[int]) -> list[dict]:
    rows: list[dict] = []
    for year in sorted(set(years)):
        zip_path = download_annual_zip(year)
        rows.extend(
            iter_observations_from_zip(
                zip_path,
                source_year=year,
                departments=("13", "20"),
                fuels=FUELS,
            )
        )
    return rows


def monthly_slice(state: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return state[
        state["eligible_publication"]
        & (state["date"] >= start)
        & (state["date"] <= end)
    ].copy()


def safe_round(value: float | int | None, digits: int = 4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def territory_stats(
    df: pd.DataFrame,
    *,
    days_in_month: int,
    corse_mean: float | None = None,
    previous_mean_by_epci: dict[tuple[str, str], float] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    if df.empty:
        return rows

    for (epci_siren, epci_nom, fuel), group in df.groupby(["epci_siren", "epci_nom", "fuel"], sort=True):
        station_means = group.groupby("station_id")["price"].mean()
        n_stations = int(group["station_id"].nunique())
        n_station_days = int(len(group))
        n_days_covered = int(group["date"].nunique())
        coverage_ratio = n_station_days / (n_stations * days_in_month) if n_stations else 0.0
        rankable = (
            n_stations >= MIN_RANK_STATIONS
            and n_days_covered >= int(days_in_month * MIN_RANK_DAY_RATIO + 0.999999)
            and coverage_ratio >= MIN_RANK_COVERAGE
        )
        mean_price = float(group["price"].mean())
        previous_mean = None
        if previous_mean_by_epci is not None:
            previous_mean = previous_mean_by_epci.get((str(epci_siren), str(fuel)))

        localities = sorted(v for v in group["localite"].dropna().astype(str).unique().tolist() if v)
        communes = sorted(v for v in group["commune"].dropna().astype(str).unique().tolist() if v)
        rows.append(
            {
                "epci_siren": str(epci_siren),
                "epci_nom": str(epci_nom),
                "fuel": str(fuel),
                "mean_eur_l": safe_round(mean_price, 4),
                "median_station_eur_l": safe_round(station_means.median(), 4),
                "observed_min_eur_l": safe_round(group["price"].min(), 4),
                "observed_max_eur_l": safe_round(group["price"].max(), 4),
                "change_vs_previous_month_cpl": None
                if previous_mean is None
                else safe_round((mean_price - previous_mean) * 100.0, 2),
                "vs_corse_cpl": None
                if corse_mean is None
                else safe_round((mean_price - corse_mean) * 100.0, 2),
                "n_stations": n_stations,
                "n_station_days": n_station_days,
                "n_days_covered": n_days_covered,
                "coverage_ratio": safe_round(coverage_ratio, 4),
                "n_communes": len(communes),
                "communes": communes,
                "localites": localities,
                "rankable": bool(rankable),
                "sample_note": None if rankable else "échantillon limité — hors classement inter-EPCI",
            }
        )
    return rows


def locality_stats(df: pd.DataFrame, *, days_in_month: int) -> list[dict]:
    rows: list[dict] = []
    if df.empty:
        return rows
    for (epci_siren, epci_nom, localite, commune, fuel), group in df.groupby(
        ["epci_siren", "epci_nom", "localite", "commune", "fuel"], sort=True
    ):
        n_stations = int(group["station_id"].nunique())
        station_means = group.groupby("station_id")["price"].mean()
        rows.append(
            {
                "epci_siren": str(epci_siren),
                "epci_nom": str(epci_nom),
                "localite": str(localite),
                "commune": str(commune),
                "fuel": str(fuel),
                "mean_eur_l": safe_round(group["price"].mean(), 4),
                "median_station_eur_l": safe_round(station_means.median(), 4),
                "observed_min_eur_l": safe_round(group["price"].min(), 4),
                "observed_max_eur_l": safe_round(group["price"].max(), 4),
                "n_stations": n_stations,
                "n_station_days": int(len(group)),
                "n_days_covered": int(group["date"].nunique()),
                "coverage_ratio": safe_round(len(group) / (n_stations * days_in_month), 4) if n_stations else 0.0,
            }
        )
    return rows


def overall_fuel_stats(df: pd.DataFrame, previous: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fuel in FUELS:
        cur = df[df["fuel"] == fuel]
        prev = previous[previous["fuel"] == fuel]
        if cur.empty:
            continue
        mean_ttc = float(cur["price"].mean())
        mean_ht = float(cur["price_ht"].mean())
        prev_ttc = None if prev.empty else float(prev["price"].mean())
        prev_ht = None if prev.empty else float(prev["price_ht"].mean())
        out[fuel] = {
            "mean_ttc_eur_l": safe_round(mean_ttc, 4),
            "mean_ht_eur_l": safe_round(mean_ht, 4),
            "change_ttc_vs_previous_month_cpl": None if prev_ttc is None else safe_round((mean_ttc - prev_ttc) * 100, 2),
            "change_ht_vs_previous_month_cpl": None if prev_ht is None else safe_round((mean_ht - prev_ht) * 100, 2),
            "n_stations": int(cur["station_id"].nunique()),
            "n_station_days": int(len(cur)),
        }
    return out


def corsica_bdr_comparison(current: pd.DataFrame, previous: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fuel in FUELS:
        cur_c = current[(current["territory"] == "Corse") & (current["fuel"] == fuel)]
        cur_b = current[(current["territory"] == "Bouches-du-Rhone") & (current["fuel"] == fuel)]
        prev_c = previous[(previous["territory"] == "Corse") & (previous["fuel"] == fuel)]
        prev_b = previous[(previous["territory"] == "Bouches-du-Rhone") & (previous["fuel"] == fuel)]
        if cur_c.empty or cur_b.empty:
            continue

        cur_ttc_gap = (float(cur_c["price"].mean()) - float(cur_b["price"].mean())) * 100.0
        cur_ht_gap = (float(cur_c["price_ht"].mean()) - float(cur_b["price_ht"].mean())) * 100.0
        prev_ttc_gap = None
        prev_ht_gap = None
        if not prev_c.empty and not prev_b.empty:
            prev_ttc_gap = (float(prev_c["price"].mean()) - float(prev_b["price"].mean())) * 100.0
            prev_ht_gap = (float(prev_c["price_ht"].mean()) - float(prev_b["price_ht"].mean())) * 100.0

        out[fuel] = {
            "corse_ttc_eur_l": safe_round(cur_c["price"].mean(), 4),
            "bdr_ttc_eur_l": safe_round(cur_b["price"].mean(), 4),
            "gap_ttc_cpl": safe_round(cur_ttc_gap, 2),
            "corse_ht_eur_l": safe_round(cur_c["price_ht"].mean(), 4),
            "bdr_ht_eur_l": safe_round(cur_b["price_ht"].mean(), 4),
            "gap_ht_cpl": safe_round(cur_ht_gap, 2),
            "gap_ttc_change_vs_previous_month_cpl": None if prev_ttc_gap is None else safe_round(cur_ttc_gap - prev_ttc_gap, 2),
            "gap_ht_change_vs_previous_month_cpl": None if prev_ht_gap is None else safe_round(cur_ht_gap - prev_ht_gap, 2),
        }
    return out


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    prev_start, prev_end = previous_month_bounds(start)
    geography_path = ROOT / args.geography
    output_path = ROOT / (args.output or f"outputs/monthly-territories-{args.month}.json")

    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("The requested month is not complete yet")

    geo = load_geography(geography_path)
    years = {prev_start.year, start.year}
    observations = load_observations(years)
    obs = pd.DataFrame(observations)
    if obs.empty:
        raise RuntimeError("No official observations parsed")
    source_max = pd.to_datetime(obs["date"]).max().normalize()
    if source_max < end:
        raise RuntimeError(f"Official source is incomplete for {args.month}: source max={source_max.date()} expected={end.date()}")

    state = build_publication_state(obs, global_end=end)
    current = monthly_slice(state, start, end)
    previous = monthly_slice(state, prev_start, prev_end)

    current_corse = current[current["territory"] == "Corse"].copy()
    previous_corse = previous[previous["territory"] == "Corse"].copy()
    current_corse = current_corse.merge(
        geo[["station_id", "localite", "commune", "epci_siren", "epci_nom"]],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
    previous_corse = previous_corse.merge(
        geo[["station_id", "localite", "commune", "epci_siren", "epci_nom"]],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
    missing_geo = sorted(current_corse.loc[current_corse["epci_siren"].isna(), "station_id"].astype(str).unique())
    if missing_geo:
        raise RuntimeError(f"Current Corsica station(s) absent from geography registry: {missing_geo}")

    days_in_month = int((end - start).days + 1)
    overall = overall_fuel_stats(current_corse, previous_corse)
    previous_epci_means = {
        (str(epci), str(fuel)): float(group["price"].mean())
        for (epci, fuel), group in previous_corse.groupby(["epci_siren", "fuel"])
    }

    epci_rows: list[dict] = []
    for fuel in FUELS:
        fuel_df = current_corse[current_corse["fuel"] == fuel]
        corse_mean = None if fuel_df.empty else float(fuel_df["price"].mean())
        epci_rows.extend(
            territory_stats(
                fuel_df,
                days_in_month=days_in_month,
                corse_mean=corse_mean,
                previous_mean_by_epci=previous_epci_means,
            )
        )

    output = {
        "meta": {
            "schema": "a4c-monthly-territories-v1",
            "month": args.month,
            "period_start": start.strftime("%Y-%m-%d"),
            "period_end": end.strftime("%Y-%m-%d"),
            "source_max_date": source_max.strftime("%Y-%m-%d"),
            "geography_file": str(Path(args.geography)),
            "geography_rows": int(len(geo)),
            "epci_count_registry": int(geo["epci_siren"].nunique()),
            "thresholds": {
                "ranking_min_stations": MIN_RANK_STATIONS,
                "ranking_min_days_ratio": MIN_RANK_DAY_RATIO,
                "ranking_min_coverage_ratio": MIN_RANK_COVERAGE,
            },
            "note": "Prototype indépendant : aucune consommation par le dashboard C2 public.",
        },
        "corse": overall,
        "corse_vs_bdr": corsica_bdr_comparison(current, previous),
        "epci": epci_rows,
        "localities": locality_stats(current_corse, days_in_month=days_in_month),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path} ({len(epci_rows)} EPCI/fuel rows)")


if __name__ == "__main__":
    main()
