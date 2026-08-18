#!/usr/bin/env python3
"""Regression-check the new c2 engine against the recovered 14-Jun-2026 snapshot.

The 49 MB historical source CSV is deliberately not committed. Pass its path explicitly,
for example after extracting `outputs/extraction-originaux/prix_corse_bdr_origine.csv`
from the user's methodology archive.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from carburantscorse2.method import build_daily_series, deduplicate_daily

EXPECTED_PATH = ROOT / "config" / "regression_expected_2026-06-14.json"


def load_legacy_source(path: Path) -> pd.DataFrame:
    dtypes = {
        "annee_fichier": str, "station_id": str, "dept_extraction": str, "cp": str,
        "ville": str, "adresse": str, "pop": str, "latitude": str, "longitude": str,
        "carburant_id": str, "carburant": str,
    }
    df = pd.read_csv(path, dtype=dtypes, encoding="utf-8-sig")
    df = df.rename(columns={
        "annee_fichier": "source_year", "dept_extraction": "department",
        "ville": "city", "adresse": "address", "carburant_id": "fuel_id",
        "carburant": "fuel", "maj": "timestamp", "prix": "price",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["date"] = df["timestamp"].dt.normalize()
    df["is_motorway"] = df["pop"].astype(str).eq("A")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_csv", type=Path)
    args = ap.parse_args()
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    source = load_legacy_source(args.source_csv)
    dedup = deduplicate_daily(source)
    series = build_daily_series(dedup, global_end=dedup["date"].max())

    got = {
        "releves_origine": len(source),
        "releves_deduplices_jour": len(dedup),
        "series_journalieres": len(series),
        "prix_aberrants_releves": int(dedup["price_aberrant"].sum()),
        "lignes_prix_aberrant": int(series["price_aberrant"].sum()),
        "lignes_gap_suspect": int(series["gap_suspect"].sum()),
        "lignes_station_inactive": int(series["station_inactive"].sum()),
        "lignes_fiables_moyennes": int(series["eligible_price_average"].sum()),
    }
    failures = []
    for key, value in expected["expected"].items():
        if got.get(key) != value:
            failures.append(f"{key}: got {got.get(key)}, expected {value}")

    grouped = (
        series.groupby(["department", "fuel"], as_index=False)
        .agg(
            rows=("price", "size"),
            reliable=("eligible_price_average", "sum"),
            aberrant=("price_aberrant", "sum"),
            gap_suspect=("gap_suspect", "sum"),
            inactive=("station_inactive", "sum"),
        )
    )
    lookup = {(str(r.department), str(r.fuel)): r for r in grouped.itertuples(index=False)}
    for row in expected["expected_by_department_fuel"]:
        key = (row["department"], row["fuel"])
        actual = lookup.get(key)
        if actual is None:
            failures.append(f"missing group {key}")
            continue
        for field in ("rows", "reliable", "aberrant", "gap_suspect", "inactive"):
            if int(getattr(actual, field)) != int(row[field]):
                failures.append(f"{key} {field}: got {getattr(actual, field)}, expected {row[field]}")

    print(json.dumps(got, ensure_ascii=False, indent=2))
    if failures:
        print("REGRESSION FAILED")
        for item in failures:
            print("-", item)
        return 1
    print("REGRESSION OK: recovered 2026-06-14 cleaning profile reproduced exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
