#!/usr/bin/env python3
"""Canonical monthly source guard with bounded, auditable BDR category backfill."""
from __future__ import annotations

import json
from pathlib import Path

import scripts.validate_monthly_source_guards as core
from scripts.monthly_bdr_category_backfill import monthly_bdr_category_resolver


def _amend(path: Path, resolvers) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    audit = resolvers[-1].audit() if resolvers else {
        "policy": {}, "applied_station_days": 0, "applied_ranges": [], "rejected_conflicts": []
    }
    payload["schema"] = "a4c-monthly-source-guards-v3"
    payload["bdr_category_backfill"] = audit
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = core.parse_args()
    start, end = core.month_bounds(args.month)
    output = core.ROOT / args.output
    resolvers = []

    def factory(legacy, registry):
        resolver = monthly_bdr_category_resolver(
            legacy,
            registry,
            window_start=start.date(),
            window_end=end.date(),
        )
        resolvers.append(resolver)
        return resolver

    core._bdr_category_resolver = factory
    try:
        core.main()
    except SystemExit:
        _amend(output, resolvers)
        raise
    else:
        _amend(output, resolvers)
        payload = json.loads(output.read_text(encoding="utf-8"))
        audit = payload.get("bdr_category_backfill") or {}
        print(
            f"Monthly BDR source guard passed with "
            f"{audit.get('applied_station_days', 0)} bounded category backfill station-day(s)"
        )


if __name__ == "__main__":
    main()
