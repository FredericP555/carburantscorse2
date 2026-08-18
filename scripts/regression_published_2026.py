#!/usr/bin/env python3
"""Network regression against the data currently embedded in index.html.

The check uses the current official annual archives and the live UFIP custom export to
reconstruct the values already published through 2026-06-06. It protects the dashboard
history before the updater is allowed to append new dates.
"""
from __future__ import annotations

from datetime import date
import json
import re
from pathlib import Path

import pandas as pd

from a4c_common.official_prices import download_annual_zip, iter_observations_from_zip
from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories
from carburantscorse2.publication_margin import build_margin_series

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = pd.Timestamp("2026-06-06")
DAILY_START = "2026-01-01"
WEEKLY_START = "2026-01-05"  # avoids the partial week beginning 2025-12-29


def parse_js_object(name: str, html: str) -> dict:
    match = re.search(rf"const\s+{re.escape(name)}=(.*?);\n", html, flags=re.S)
    if not match:
        raise RuntimeError(f"Cannot find const {name} in index.html")
    raw = match.group(1)
    quoted = re.sub(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', raw)
    return json.loads(quoted)


def trim(rows: list[dict], start: str, end: str) -> list[dict]:
    return [r for r in rows if start <= r["date"] <= end]


def compare(label: str, actual: list[dict], expected: list[dict], start: str) -> None:
    a = trim(actual, start, CUTOFF.strftime("%Y-%m-%d"))
    e = trim(expected, start, CUTOFF.strftime("%Y-%m-%d"))
    if a != e:
        amap = {r["date"]: r for r in a}
        emap = {r["date"]: r for r in e}
        dates = sorted(set(amap) | set(emap))
        differences = [(d, amap.get(d), emap.get(d)) for d in dates if amap.get(d) != emap.get(d)]
        preview = "\n".join(f"  {d}: actual={av} expected={ev}" for d, av, ev in differences[:12])
        raise AssertionError(
            f"{label}: {len(differences)} differences; actual={len(a)} expected={len(e)}\n{preview}"
        )
    print(f"OK {label}: {len(a)} points")


def main() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    embedded = parse_js_object("DATA", html)
    embedded_margins = parse_js_object("MARGES_GZ", html)

    observations = []
    for year in (2025, 2026):
        path = download_annual_zip(year)
        observations.extend(
            iter_observations_from_zip(
                path,
                source_year=year,
                departments=("13", "20"),
                fuels=("Gazole", "SP95", "E10"),
            )
        )
    obs = pd.DataFrame(observations)
    categories = load_bdr_categories(ROOT / "config" / "bdr_categories_published_2026-06-06.csv")
    state = build_publication_state(obs, global_end=CUTOFF, bdr_categories=categories)

    cases = [
        ("Gazole / toutes BDR", "Gazole", "Gazole", "all", "gazole", "sp95", "all"),
        ("Gazole / réseau BDR", "Gazole", "Gazole", "network", "gazole", "sp95", "reseau"),
        ("SP95 / toutes BDR SP95", "SP95", "SP95", "all", "sp95", "sp95", "all"),
        ("SP95 / réseau BDR SP95", "SP95", "SP95", "network", "sp95", "sp95", "reseau"),
        ("SP95 / toutes BDR E10", "SP95", "E10", "all", "sp95", "e10", "all"),
        ("SP95 / réseau BDR E10", "SP95", "E10", "network", "sp95", "e10", "reseau"),
    ]

    for label, corsica_fuel, bdr_fuel, scope, key, ref, group in cases:
        daily = build_gap_series(
            state,
            corsica_fuel=corsica_fuel,
            bdr_fuel=bdr_fuel,
            bdr_scope=scope,
            granularity="daily",
        )
        compare(f"{label} daily", daily, embedded[key][ref]["daily"][group], DAILY_START)
        weekly = build_gap_series(
            state,
            corsica_fuel=corsica_fuel,
            bdr_fuel=bdr_fuel,
            bdr_scope=scope,
            granularity="weekly",
        )
        compare(f"{label} weekly", weekly, embedded[key][ref]["weekly"][group], WEEKLY_START)

    print("Published 2026 price regression: PASS")

    # Fetch a little history before 1 Jan so the first calendar days can be forward-filled
    # even if UFIP has no observation on New Year's Day itself.
    ufip_start = date(2025, 12, 15)
    ufip_end = CUTOFF.date()
    rot_observed = fetch_rotterdam_gazole(ufip_start, ufip_end)
    rot_daily = expand_daily(rot_observed, ufip_start, ufip_end)
    margin_state = state[state["date"] >= pd.Timestamp("2026-01-01")].copy()

    margin_all = build_margin_series(margin_state, rot_daily, bdr_scope="all")
    compare("Gazole margin / toutes BDR", margin_all, embedded_margins["all"], WEEKLY_START)
    margin_network = build_margin_series(margin_state, rot_daily, bdr_scope="network")
    compare("Gazole margin / réseau BDR", margin_network, embedded_margins["reseau"], WEEKLY_START)
    print("Published 2026 margin regression: PASS")


if __name__ == "__main__":
    main()
