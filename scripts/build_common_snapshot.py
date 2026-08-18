#!/usr/bin/env python3
"""Build the shared A4C normalized daily-observation snapshot from official ZIPs."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.official_prices import (
    deduplicate_daily,
    download_annual_zip,
    iter_observations_from_zip,
    write_normalized_csv,
)


def parse_years(raw: str) -> list[int]:
    if ":" in raw:
        a, b = raw.split(":", 1)
        start, end = int(a), int(b)
        return list(range(start, end + 1))
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default=f"2022:{date.today().year}")
    parser.add_argument("--output", default="outputs/common/official_observations_daily.csv")
    parser.add_argument("--cache-dir", default=".cache/official-fuel")
    args = parser.parse_args()

    rows = []
    for year in parse_years(args.years):
        zip_path = download_annual_zip(year, cache_dir=Path(args.cache_dir))
        rows.extend(iter_observations_from_zip(zip_path, source_year=year))
    dedup = deduplicate_daily(rows)
    count = write_normalized_csv(dedup, Path(args.output))
    print(f"Wrote {count:,} common daily observations to {args.output}")


if __name__ == "__main__":
    main()
