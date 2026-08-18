#!/usr/bin/env python3
"""Download UFIP Rotterdam Gazole and write raw + daily forward-filled CSVs."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole


def parse_iso(raw: str) -> date:
    return date.fromisoformat(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=parse_iso, default=date(date.today().year, 1, 1))
    parser.add_argument("--end", type=parse_iso, default=date.today())
    parser.add_argument("--output-dir", default="outputs/ufip")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    observed = fetch_rotterdam_gazole(args.start, args.end)
    daily = expand_daily(observed, args.start, args.end)
    observed.to_csv(out / "rotterdam_gazole_observed.csv", index=False)
    daily.to_csv(out / "rotterdam_gazole_daily.csv", index=False)
    print(f"UFIP observed rows: {len(observed):,}; daily calendar rows: {len(daily):,}")
    if not observed.empty:
        print(f"UFIP range: {observed['date'].min()} -> {observed['date'].max()}")


if __name__ == "__main__":
    main()
