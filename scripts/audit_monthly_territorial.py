#!/usr/bin/env python3
"""Audit the isolated monthly territorial prototype at station level.

This script is deliberately separate from the public C2 workflow. It checks whether
territorial rankings are being driven by stale forward-filled station states and computes
a more robust within-EPCI spread based on each station's monthly mean rather than the
single lowest/highest daily price seen during the month.
"""
from __future__ import annotations

import argparse
import calendar
import json
from datetime import date
from pathlib import Path

import pandas as pd

from a4c_common.official_prices import download_annual_zip, iter_observations_from_zip
from carburantscorse2.publication import build_publication_state

ROOT = Path(__file__).resolve().parents[1]
FUELS = ("Gazole", "SP95")


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True, help="Complete month YYYY-MM")
    p.add_argument("--geography", default="config/corse_station_geography_2026.csv")
    p.add_argument("--output", default=None)
    p.add_argument("--summary", default=None)
    return p.parse_args()


def bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    year, mon = (int(v) for v in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return pd.Timestamp(year, mon, 1), pd.Timestamp(year, mon, last)


def r(value, digits=4):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def main() -> None:
    a = args()
    start, end = bounds(a.month)
    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("Requested month is not complete")

    geo = pd.read_csv(ROOT / a.geography, dtype=str).fillna("")
    if geo["station_id"].duplicated().any():
        raise RuntimeError("Duplicate station_id in geography registry")

    zip_path = download_annual_zip(start.year)
    obs = list(iter_observations_from_zip(
        zip_path,
        source_year=start.year,
        departments=("20",),
        fuels=FUELS,
    ))
    frame = pd.DataFrame(obs)
    if frame.empty:
        raise RuntimeError("No Corsica observations parsed")
    source_max = pd.to_datetime(frame["date"]).max().normalize()
    if source_max < end:
        raise RuntimeError(f"Official source incomplete: {source_max.date()} < {end.date()}")

    state = build_publication_state(frame, global_end=end)
    cur = state[
        state["eligible_publication"]
        & state["territory"].eq("Corse")
        & state["date"].between(start, end)
        & state["fuel"].isin(FUELS)
    ].copy()
    cur = cur.merge(
        geo[["station_id", "localite", "commune", "epci_siren", "epci_nom"]],
        on="station_id",
        how="left",
        validate="many_to_one",
    )
    missing = sorted(cur.loc[cur["epci_siren"].isna(), "station_id"].astype(str).unique())
    if missing:
        raise RuntimeError(f"Stations absent from geography registry: {missing}")

    cur["source_timestamp"] = pd.to_datetime(cur["source_timestamp"], errors="coerce")
    days = (end - start).days + 1
    station_rows = []
    for (sid, epci, epci_nom, commune, localite, fuel), g in cur.groupby(
        ["station_id", "epci_siren", "epci_nom", "commune", "localite", "fuel"], sort=True
    ):
        real = g[g["real_observation"].fillna(False).astype(bool)]
        latest_source = g["source_timestamp"].max()
        last_source_date = None if pd.isna(latest_source) else pd.Timestamp(latest_source).normalize()
        stale_at_end = None if last_source_date is None else int((end - last_source_date).days)
        station_rows.append({
            "station_id": str(sid),
            "epci_siren": str(epci),
            "epci_nom": str(epci_nom),
            "commune": str(commune),
            "localite": str(localite),
            "fuel": str(fuel),
            "mean_eur_l": r(g["price"].mean()),
            "min_eur_l": r(g["price"].min()),
            "max_eur_l": r(g["price"].max()),
            "eligible_days": int(g["date"].nunique()),
            "coverage_ratio": r(g["date"].nunique() / days, 4),
            "real_declarations_in_month": int(len(real)),
            "last_real_declaration_in_month": None if real.empty else pd.Timestamp(real["date"].max()).strftime("%Y-%m-%d"),
            "last_source_declaration_used": None if last_source_date is None else last_source_date.strftime("%Y-%m-%d"),
            "source_age_days_at_month_end": stale_at_end,
            "carried_all_month": bool(real.empty),
        })

    stations = pd.DataFrame(station_rows)
    epci_audit = []
    for (epci, epci_nom, fuel), g in stations.groupby(["epci_siren", "epci_nom", "fuel"], sort=True):
        means = g["mean_eur_l"].astype(float)
        carried = int(g["carried_all_month"].sum())
        epci_audit.append({
            "epci_siren": str(epci),
            "epci_nom": str(epci_nom),
            "fuel": str(fuel),
            "n_stations": int(len(g)),
            "station_month_mean_min_eur_l": r(means.min()),
            "station_month_mean_median_eur_l": r(means.median()),
            "station_month_mean_max_eur_l": r(means.max()),
            "station_month_mean_spread_cpl": r((means.max() - means.min()) * 100, 2),
            "stations_carried_all_month": carried,
            "share_carried_all_month": r(carried / len(g), 4),
            "max_source_age_days_at_month_end": None if g["source_age_days_at_month_end"].dropna().empty else int(g["source_age_days_at_month_end"].dropna().max()),
        })

    out = {
        "meta": {
            "schema": "a4c-monthly-territorial-audit-v1",
            "month": a.month,
            "period_start": start.strftime("%Y-%m-%d"),
            "period_end": end.strftime("%Y-%m-%d"),
            "official_source_max_date": source_max.strftime("%Y-%m-%d"),
            "note": "Audit interne du prototype ; aucune consommation par le dashboard public.",
        },
        "epci_audit": epci_audit,
        "stations": station_rows,
    }

    output = ROOT / (a.output or f"outputs/monthly-territories-{a.month}-audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f"# Audit stationnel territorial — {a.month}", ""]
    lines.append(f"Source officielle disponible jusqu'au : {source_max.strftime('%Y-%m-%d')}.")
    lines.append(f"Couples station/carburant audités : {len(stations)}.")
    lines.append("")
    for fuel in FUELS:
        sf = stations[stations["fuel"].eq(fuel)]
        ef = [x for x in epci_audit if x["fuel"] == fuel]
        carried = sf[sf["carried_all_month"]]
        lines.append(f"## {fuel}")
        lines.append(f"Stations éligibles : {sf['station_id'].nunique()} ; sans déclaration réelle dans le mois : {len(carried)}.")
        lines.append("")
        lines.append("### Dispersion robuste par EPCI (moyennes mensuelles par station)")
        lines.append("| EPCI | Stations | Min moy. station | Médiane | Max moy. station | Écart | Portées tout le mois |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for e in sorted(ef, key=lambda x: x["station_month_mean_spread_cpl"], reverse=True):
            lines.append(
                f"| {e['epci_nom']} | {e['n_stations']} | {e['station_month_mean_min_eur_l']:.4f} | "
                f"{e['station_month_mean_median_eur_l']:.4f} | {e['station_month_mean_max_eur_l']:.4f} | "
                f"{e['station_month_mean_spread_cpl']:.2f} c/L | {e['stations_carried_all_month']} |"
            )
        lines.append("")
        if not carried.empty:
            lines.append("### Stations sans déclaration réelle pendant le mois")
            for _, s in carried.sort_values(["epci_nom", "localite", "station_id"]).iterrows():
                lines.append(
                    f"- {s['station_id']} — {s['localite']} ({s['epci_nom']}) : moyenne {s['mean_eur_l']:.4f} €/L, "
                    f"dernière déclaration source utilisée {s['last_source_declaration_used']}, âge fin de mois {s['source_age_days_at_month_end']} j."
                )
            lines.append("")

    summary = ROOT / (a.summary or f"outputs/monthly-territories-{a.month}-audit.md")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
