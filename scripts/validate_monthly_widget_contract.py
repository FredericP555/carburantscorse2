#!/usr/bin/env python3
"""Fail closed if the territorial monthly JSON and widget drift apart."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

FUELS = ("Gazole", "SP95")
SCOPES = ("all", "network")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--widget", required=True)
    return p.parse_args()


def require_keys(obj: dict, keys: set[str], context: str) -> None:
    missing = sorted(keys.difference(obj))
    if missing:
        raise RuntimeError(f"{context}: missing key(s): {missing}")


def number(value, context: str, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{context}: expected numeric value, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{context}: non-finite numeric value")
    return result


def main() -> None:
    args = parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    html = Path(args.widget).read_text(encoding="utf-8")

    require_keys(data, {"meta", "corse", "corse_vs_bdr", "epci", "localities"}, "monthly JSON")
    meta = data["meta"]
    if meta.get("schema") != "a4c-monthly-territories-v2-c2-engine":
        raise RuntimeError(f"Unexpected monthly schema: {meta.get('schema')}")
    epci_count = int(meta.get("epci_count_registry", 0))
    if epci_count != 19:
        raise RuntimeError(f"Expected 19 EPCI in registry, got {epci_count}")
    if int(meta.get("geography_rows", 0)) < epci_count:
        raise RuntimeError("geography_rows is implausibly smaller than EPCI count")

    epci_required = {
        "epci_siren", "epci_nom", "fuel", "mean_eur_l", "median_station_eur_l",
        "station_mean_min_eur_l", "station_mean_max_eur_l", "station_mean_spread_cpl",
        "change_vs_previous_month_cpl", "vs_corse_cpl", "n_stations", "n_station_days",
        "n_days_covered", "coverage_ratio", "n_communes", "rankable",
    }
    locality_required = {
        "epci_siren", "epci_nom", "localite", "commune", "fuel", "mean_eur_l",
        "station_mean_min_eur_l", "station_mean_max_eur_l", "n_stations",
    }

    rows = data["epci"]
    if not isinstance(rows, list) or len(rows) != 38:
        raise RuntimeError(f"Expected exactly 38 EPCI/fuel rows, got {len(rows) if isinstance(rows, list) else type(rows).__name__}")
    keys = [(str(r.get("epci_siren")), str(r.get("fuel"))) for r in rows]
    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate EPCI/fuel row detected")

    for i, row in enumerate(rows):
        context = f"epci[{i}]"
        require_keys(row, epci_required, context)
        if row["fuel"] not in FUELS:
            raise RuntimeError(f"{context}: unexpected fuel {row['fuel']!r}")
        if not str(row["epci_siren"]).isdigit():
            raise RuntimeError(f"{context}: invalid epci_siren")
        if not str(row["epci_nom"]).strip():
            raise RuntimeError(f"{context}: empty epci_nom")
        mean = number(row["mean_eur_l"], f"{context}.mean_eur_l")
        med = number(row["median_station_eur_l"], f"{context}.median_station_eur_l")
        lo = number(row["station_mean_min_eur_l"], f"{context}.station_mean_min_eur_l")
        hi = number(row["station_mean_max_eur_l"], f"{context}.station_mean_max_eur_l")
        spread = number(row["station_mean_spread_cpl"], f"{context}.station_mean_spread_cpl")
        number(row["change_vs_previous_month_cpl"], f"{context}.change_vs_previous_month_cpl", allow_none=True)
        number(row["vs_corse_cpl"], f"{context}.vs_corse_cpl", allow_none=True)
        if not (0 < lo <= med <= hi < 5):
            raise RuntimeError(f"{context}: inconsistent station mean range")
        if abs((hi - lo) * 100 - spread) > 0.02:
            raise RuntimeError(f"{context}: spread disagrees with station min/max")
        if not (lo - 1e-9 <= mean <= hi + 1e-9):
            raise RuntimeError(f"{context}: territory mean outside station mean range")
        for key in ("n_stations", "n_station_days", "n_days_covered", "n_communes"):
            if isinstance(row[key], bool) or not isinstance(row[key], int) or row[key] < 0:
                raise RuntimeError(f"{context}.{key}: expected non-negative integer")
        coverage = number(row["coverage_ratio"], f"{context}.coverage_ratio")
        if not 0 <= coverage <= 1:
            raise RuntimeError(f"{context}.coverage_ratio outside [0,1]")
        if not isinstance(row["rankable"], bool):
            raise RuntimeError(f"{context}.rankable must be boolean")

    localities = data["localities"]
    if not isinstance(localities, list) or not localities:
        raise RuntimeError("localities must be a non-empty list")
    locality_keys = []
    for i, row in enumerate(localities):
        context = f"localities[{i}]"
        require_keys(row, locality_required, context)
        locality_keys.append((str(row["epci_siren"]), str(row["fuel"]), str(row["localite"]), str(row["commune"])))
        number(row["mean_eur_l"], f"{context}.mean_eur_l")
        number(row["station_mean_min_eur_l"], f"{context}.station_mean_min_eur_l")
        number(row["station_mean_max_eur_l"], f"{context}.station_mean_max_eur_l")
    if len(locality_keys) != len(set(locality_keys)):
        raise RuntimeError("Duplicate locality/fuel rows detected")

    for fuel in FUELS:
        fuel_rows = [r for r in rows if r["fuel"] == fuel]
        sirens = {r["epci_siren"] for r in fuel_rows}
        if len(fuel_rows) != epci_count or len(sirens) != epci_count:
            raise RuntimeError(f"{fuel}: expected exactly {epci_count} unique EPCI rows")
        corse = data["corse"].get(fuel, {})
        require_keys(corse, {"mean_ttc_eur_l", "mean_ht_eur_l", "n_stations", "n_station_days"}, f"corse/{fuel}")
        number(corse["mean_ttc_eur_l"], f"corse/{fuel}/mean_ttc_eur_l")
        number(corse["mean_ht_eur_l"], f"corse/{fuel}/mean_ht_eur_l")
        for scope in SCOPES:
            cmp = ((data["corse_vs_bdr"].get(fuel) or {}).get(scope) or {})
            require_keys(
                cmp,
                {"gap_ttc_cpl", "gap_ht_cpl", "valid_days", "guard_failed_days",
                 "corse_ttc_eur_l", "bdr_ttc_eur_l", "corse_ht_eur_l", "bdr_ht_eur_l"},
                f"corse_vs_bdr/{fuel}/{scope}",
            )
            for key in ("gap_ttc_cpl", "gap_ht_cpl", "corse_ttc_eur_l", "bdr_ttc_eur_l", "corse_ht_eur_l", "bdr_ht_eur_l"):
                number(cmp[key], f"corse_vs_bdr/{fuel}/{scope}/{key}")
            if not isinstance(cmp["valid_days"], int) or not isinstance(cmp["guard_failed_days"], int):
                raise RuntimeError(f"corse_vs_bdr/{fuel}/{scope}: day counters must be integers")
            if cmp["valid_days"] + cmp["guard_failed_days"] <= 0:
                raise RuntimeError(f"corse_vs_bdr/{fuel}/{scope}: invalid day counters")

    for token in ("observed_min_eur_l", "observed_max_eur_l"):
        if token in html:
            raise RuntimeError(f"Widget still references legacy field {token}")
    for token in ("station_mean_min_eur_l", "station_mean_max_eur_l", "bdrScope"):
        if token not in html:
            raise RuntimeError(f"Widget does not consume required token {token}")
    if "50 L" in html or "50L" in html:
        raise RuntimeError("Widget must not impose a fixed 50-litre volume")
    if "gap_ttc_cpl" not in html or "gap_ht_cpl" not in html:
        raise RuntimeError("Widget must expose TTC consumer gap and HT analytical gap separately")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.I | re.S)
    inline = [s for s in scripts if s.strip()]
    if not inline:
        raise RuntimeError("No inline JavaScript found in widget")
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as fh:
        fh.write("\n".join(inline))
        js_path = fh.name
    result = subprocess.run(["node", "--check", js_path], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Widget JavaScript syntax error:\n{result.stderr}")

    non_rankable = sum(1 for r in rows if not r["rankable"])
    print(
        f"Monthly widget contract OK: schema={meta['schema']}; EPCI={epci_count}; "
        f"rows={len(rows)} unique; non-rankable={non_rankable}; numeric contract OK; JS syntax OK"
    )


if __name__ == "__main__":
    main()
