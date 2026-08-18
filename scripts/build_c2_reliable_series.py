#!/usr/bin/env python3
"""Apply the recovered c2 reliability profile to the shared observation snapshot."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pandas as pd

from carburantscorse2.method import add_tax_fields, build_daily_series, deduplicate_daily


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/common/official_observations_daily.csv")
    parser.add_argument("--output-dir", default="outputs/c2")
    args = parser.parse_args()

    inp = Path(args.input)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(inp, low_memory=False)
    dedup = deduplicate_daily(raw)
    daily = add_tax_fields(build_daily_series(dedup))
    daily.to_csv(outdir / "series_daily_all.csv", index=False)
    daily[daily["eligible_price_average"]].to_csv(outdir / "series_daily_reliable.csv", index=False)
    summary = (
        daily.groupby(["territory", "fuel"])
        .agg(
            rows=("price", "size"),
            reliable_rows=("eligible_price_average", "sum"),
            stations=("station_id", "nunique"),
            price_aberrant=("price_aberrant", "sum"),
            gap_suspect=("gap_suspect", "sum"),
            station_inactive=("station_inactive", "sum"),
        )
        .reset_index()
    )
    summary.to_csv(outdir / "summary_by_territory_fuel.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
