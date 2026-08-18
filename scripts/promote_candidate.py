#!/usr/bin/env python3
"""Promote a validated append-only candidate to data.json.

The script refuses any historical rewrite. It is intentionally separate from the live
builder so CI can inspect a candidate before production promotion.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def iter_public_series(obj: dict):
    data = obj["DATA"]
    for key, refs in data.items():
        for ref, grans in refs.items():
            for gran, groups in grans.items():
                for group, rows in groups.items():
                    yield f"DATA/{key}/{ref}/{gran}/{group}", rows
    for group, rows in obj["MARGES_GZ"].items():
        yield f"MARGES_GZ/{group}", rows


def write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="outputs/candidate-data.json")
    parser.add_argument("--summary", default="outputs/candidate-summary.json")
    parser.add_argument("--target", default="data.json")
    args = parser.parse_args()

    candidate_path = ROOT / args.candidate
    summary_path = ROOT / args.summary
    target_path = ROOT / args.target
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    baseline = json.loads(target_path.read_text(encoding="utf-8"))

    if summary.get("blocking_unknown_bdr_station_count") != 0:
        raise SystemExit("Refusing promotion: unclassified recent BDR station(s)")
    if candidate.get("meta", {}).get("publication_mode") != "append-only":
        raise SystemExit("Refusing promotion: candidate is not append-only")

    source_max = candidate["meta"].get("official_source_max_date")
    target_end = candidate["meta"].get("daily_target_end")
    if not source_max or not target_end or target_end > source_max:
        raise SystemExit(f"Refusing promotion: target_end={target_end} source_max={source_max}")

    baseline_series = dict(iter_public_series(baseline))
    candidate_series = dict(iter_public_series(candidate))
    if set(baseline_series) != set(candidate_series):
        raise SystemExit("Refusing promotion: public series topology changed")

    for name, old_rows in baseline_series.items():
        new_rows = candidate_series[name]
        if len(new_rows) < len(old_rows):
            raise SystemExit(f"Refusing promotion: {name} shrank")
        if new_rows[: len(old_rows)] != old_rows:
            raise SystemExit(f"Refusing promotion: historical rewrite detected in {name}")
        dates = [row["date"] for row in new_rows]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise SystemExit(f"Refusing promotion: invalid date ordering in {name}")

    additions = summary.get("additions", {})
    total_additions = sum(int(v) for v in additions.values())
    if total_additions == 0:
        print("No new public point: data.json stays unchanged")
        write_output("changed", "false")
        return

    # Use the exact compact candidate bytes produced by the builder.
    target_path.write_text(candidate_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Promoted candidate: {total_additions} new public points")
    write_output("changed", "true")
    write_output("total_additions", str(total_additions))
    write_output("daily_target_end", str(target_end))
    write_output("weekly_complete_through", str(candidate["meta"].get("weekly_complete_through", "")))


if __name__ == "__main__":
    main()
