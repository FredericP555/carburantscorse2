#!/usr/bin/env python3
"""Preflight guard for the future monthly territorial automation.

This script does not publish anything and does not modify C2 data.json. It answers one
question only: after a successful C2 cycle, is the immediately preceding calendar month
eligible to enter the monthly generation chain?

The guard is intentionally conservative. It requires a complete prior month, a C2 reference
whose validated daily target extends into the new month, the exact C1 release tag already
pinned by C2, a complete 19-EPCI geography registry, and no existing final monthly receipt.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--c2-data", default="data.json")
    p.add_argument("--geography", default="config/corse_station_geography_2026.csv")
    p.add_argument("--receipt-dir", default="outputs/monthly-receipts")
    p.add_argument("--month", help="Expected month YYYY-MM; defaults to prior calendar month")
    p.add_argument("--as-of", help="Local calendar date YYYY-MM-DD; defaults to today")
    p.add_argument("--allow-backfill", action="store_true")
    p.add_argument("--output")
    p.add_argument("--fail-if-not-ready", action="store_true")
    return p.parse_args()


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        last = calendar.monthrange(y, m)[1]
        return date(y, m, 1), date(y, m, last)
    except Exception as exc:
        raise SystemExit("month must be YYYY-MM") from exc


def previous_calendar_month(as_of: date) -> str:
    first = as_of.replace(day=1)
    prev = first - pd.Timedelta(days=1)
    return prev.strftime("%Y-%m")


def add_check(checks: list[dict], key: str, ok: bool, detail: str) -> None:
    checks.append({"key": key, "ok": bool(ok), "detail": detail})


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    auto_month = previous_calendar_month(as_of)
    month = args.month or auto_month
    start, end = month_bounds(month)
    checks: list[dict] = []

    add_check(checks, "month_complete", end < as_of, f"month_end={end.isoformat()}, as_of={as_of.isoformat()}")
    add_check(
        checks,
        "is_previous_calendar_month",
        args.allow_backfill or month == auto_month,
        f"requested={month}, previous_calendar_month={auto_month}, allow_backfill={args.allow_backfill}",
    )

    c2_path = resolve(args.c2_data)
    c2 = json.loads(c2_path.read_text(encoding="utf-8"))
    meta = dict(c2.get("meta") or {})
    v2 = dict(meta.get("v2") or {})
    release_tag = v2.get("c1_release_tag") or meta.get("official_shared_release_tag")
    daily_target_raw = meta.get("daily_target_end") or meta.get("official_shared_source_max_date")
    daily_target = date.fromisoformat(str(daily_target_raw)[:10]) if daily_target_raw else None

    add_check(checks, "c1_release_pinned", bool(release_tag), f"c1_release_tag={release_tag!s}")
    add_check(
        checks,
        "c2_complete_through_month_end",
        daily_target is not None and daily_target >= end,
        f"c2_daily_target_end={daily_target.isoformat() if daily_target else None}, month_end={end.isoformat()}",
    )
    # The monthly chain must be entered only after a genuinely new-month successful C2 state,
    # not merely because the previous month's final day exists in a stale reference.
    add_check(
        checks,
        "c2_success_state_is_post_month_end",
        daily_target is not None and daily_target > end,
        f"c2_daily_target_end={daily_target.isoformat() if daily_target else None}, required_after={end.isoformat()}",
    )

    geo_path = resolve(args.geography)
    geo = pd.read_csv(geo_path, dtype=str).fillna("")
    required = {"station_id", "epci_siren", "epci_nom", "commune"}
    missing_cols = sorted(required.difference(geo.columns))
    add_check(checks, "geography_columns", not missing_cols, f"missing_columns={missing_cols}")
    duplicate_ids = [] if "station_id" not in geo.columns else sorted(geo.loc[geo["station_id"].duplicated(keep=False), "station_id"].unique())
    add_check(checks, "geography_unique_station_ids", not duplicate_ids, f"duplicate_station_ids={duplicate_ids[:10]}")
    if not missing_cols:
        incomplete = geo[(geo["station_id"].str.strip()=="") | (geo["commune"].str.strip()=="") | (geo["epci_siren"].str.strip()=="") | (geo["epci_nom"].str.strip()=="")]
        epci_count = int(geo["epci_siren"].nunique())
        add_check(checks, "geography_complete_rows", incomplete.empty, f"incomplete_rows={len(incomplete)}")
        add_check(checks, "geography_has_19_epci", epci_count == 19, f"epci_count={epci_count}, station_rows={len(geo)}")
    else:
        epci_count = None
        add_check(checks, "geography_complete_rows", False, "cannot evaluate because required columns are missing")
        add_check(checks, "geography_has_19_epci", False, "cannot evaluate because required columns are missing")

    receipt_dir = resolve(args.receipt_dir)
    receipt_path = receipt_dir / f"{month}.json"
    already_processed = receipt_path.exists()
    add_check(checks, "month_not_already_finalized", not already_processed, f"receipt={receipt_path}, exists={already_processed}")

    ready = all(c["ok"] for c in checks)
    result = {
        "schema": "a4c-monthly-readiness-v1",
        "ready": ready,
        "month": month,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "as_of": as_of.isoformat(),
        "c2_daily_target_end": daily_target.isoformat() if daily_target else None,
        "c1_release_tag": release_tag,
        "geography_rows": int(len(geo)),
        "epci_count": epci_count,
        "receipt_path": str(receipt_path),
        "checks": checks,
        "next_action": "generate_monthly_dataset" if ready else "do_not_generate",
    }

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(text, end="")
    if args.output:
        out = resolve(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    if args.fail_if_not_ready and not ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
