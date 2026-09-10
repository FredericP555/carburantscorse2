#!/usr/bin/env python3
"""Fail closed if the territorial widget and monthly JSON drift apart.

This validation is deliberately lightweight and dependency-free. It checks the fields consumed by
the HTML widget, the two C2 Bouches-du-Rhône scopes, the 19-EPCI fuel coverage, removal of legacy
min/max field names, and JavaScript syntax with the Node runtime available on GitHub Actions.
"""
from __future__ import annotations

import argparse
import json
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


def main() -> None:
    args = parse_args()
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    html = Path(args.widget).read_text(encoding="utf-8")

    require_keys(data, {"meta", "corse", "corse_vs_bdr", "epci", "localities"}, "monthly JSON")
    if data["meta"].get("schema") != "a4c-monthly-territories-v2-c2-engine":
        raise RuntimeError(f"Unexpected monthly schema: {data['meta'].get('schema')}")
    epci_count = int(data["meta"].get("epci_count_registry", 0))
    if epci_count != 19:
        raise RuntimeError(f"Expected 19 EPCI in registry, got {epci_count}")

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
    for i, row in enumerate(data["epci"]):
        require_keys(row, epci_required, f"epci[{i}]")
    for i, row in enumerate(data["localities"]):
        require_keys(row, locality_required, f"localities[{i}]")

    for fuel in FUELS:
        rows = [r for r in data["epci"] if r.get("fuel") == fuel]
        unique = {r["epci_siren"] for r in rows}
        if len(unique) != epci_count:
            raise RuntimeError(f"{fuel}: expected {epci_count} EPCI rows, got {len(unique)}")
        require_keys(data["corse"].get(fuel, {}), {"mean_ttc_eur_l", "mean_ht_eur_l"}, f"corse/{fuel}")
        for scope in SCOPES:
            cmp = ((data["corse_vs_bdr"].get(fuel) or {}).get(scope) or {})
            require_keys(
                cmp,
                {"gap_ttc_cpl", "gap_ht_cpl", "valid_days", "guard_failed_days",
                 "corse_ttc_eur_l", "bdr_ttc_eur_l"},
                f"corse_vs_bdr/{fuel}/{scope}",
            )

    legacy_tokens = ("observed_min_eur_l", "observed_max_eur_l")
    for token in legacy_tokens:
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
    js = "\n".join(inline)
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as fh:
        fh.write(js)
        js_path = fh.name
    result = subprocess.run(["node", "--check", js_path], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Widget JavaScript syntax error:\n{result.stderr}")

    non_rankable = sum(1 for r in data["epci"] if not r["rankable"])
    print(
        f"Monthly widget contract OK: schema={data['meta']['schema']}; "
        f"EPCI={epci_count}; rows={len(data['epci'])}; non-rankable fuel/EPCI rows={non_rankable}; JS syntax OK"
    )


if __name__ == "__main__":
    main()
