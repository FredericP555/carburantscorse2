#!/usr/bin/env python3
"""Fetch the Rotterdam Gazole assets already downloaded and published by C1.

This script deliberately never contacts UFIP. It reuses the exact C1 shared release
that precedes C2 in the weekly automation chain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a4c_common.shared_release import download_shared_rotterdam_assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/ufip")
    args = parser.parse_args()
    result = download_shared_rotterdam_assets(Path(args.output_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
