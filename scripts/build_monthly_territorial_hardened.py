#!/usr/bin/env python3
"""Canonical monthly builder with bounded BDR category backfill.

The underlying calculations remain in build_monthly_territorial.py.  This entry point changes only
the BDR category resolver used while reconstructing the requested month and the immediately
preceding month.  It then records the applied category backfills in the internal audit.
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.build_monthly_territorial as core
from scripts.monthly_bdr_category_backfill import monthly_bdr_category_resolver


def main() -> None:
    args = core.parse_args()
    start, end = core.month_bounds(args.month)
    prev_start, _prev_end = core.previous_month_bounds(start)
    resolvers = []

    def factory(legacy, registry):
        resolver = monthly_bdr_category_resolver(
            legacy,
            registry,
            window_start=prev_start.date(),
            window_end=end.date(),
        )
        resolvers.append(resolver)
        return resolver

    # Only this monthly module variable is replaced. C2 production code and files are untouched.
    core._bdr_category_resolver = factory
    core.main()

    output = Path(args.output or f"outputs/monthly-territories-{args.month}.json")
    if not output.is_absolute():
        output = core.ROOT / output
    payload = json.loads(output.read_text(encoding="utf-8"))
    audit = resolvers[-1].audit() if resolvers else {
        "policy": {}, "applied_station_days": 0, "applied_ranges": [], "rejected_conflicts": []
    }
    payload.setdefault("meta", {})["bdr_category_backfill"] = audit.get("policy", {})
    payload.setdefault("internal_audit", {})["bdr_category_backfill"] = audit
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Monthly BDR category backfill: {audit.get('applied_station_days', 0)} station-day(s), "
        f"{len(audit.get('rejected_conflicts', []))} conflict rejection(s)"
    )


if __name__ == "__main__":
    main()
