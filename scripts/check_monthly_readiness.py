#!/usr/bin/env python3
"""Fail-closed preflight guard for the future monthly territorial automation.

A calendar rollover is not enough. The guard requires a C2 business-success receipt proving
that the exact repository data/summary were promoted and observed on Pages, plus the exact C1
release provenance already consumed by C2. It never publishes and never modifies C2 data.json.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FINAL_RECEIPT_SCHEMA = "a4c-monthly-final-receipt-v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--c2-data", default="data.json")
    p.add_argument("--c2-summary", default="homepage-summary.json")
    p.add_argument("--c2-business-receipt", required=True)
    p.add_argument("--expected-c2-commit")
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def month_bounds(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    except Exception as exc:
        raise SystemExit("month must be YYYY-MM") from exc


def previous_calendar_month(as_of: date) -> str:
    first = as_of.replace(day=1)
    return (first - pd.Timedelta(days=1)).strftime("%Y-%m")


def add_check(checks: list[dict], key: str, ok: bool, detail: str) -> None:
    checks.append({"key": key, "ok": bool(ok), "detail": detail})


def load_object(path: Path, label: str) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(obj, dict):
        raise RuntimeError(f"{label} JSON root is not an object: {path}")
    return obj


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    auto_month = previous_calendar_month(as_of)
    month = args.month or auto_month
    start, end = month_bounds(month)
    checks: list[dict] = []

    add_check(checks, "month_complete", end < as_of, f"month_end={end}, as_of={as_of}")
    add_check(
        checks,
        "is_previous_calendar_month",
        args.allow_backfill or month == auto_month,
        f"requested={month}, previous_calendar_month={auto_month}, allow_backfill={args.allow_backfill}",
    )

    c2_path = resolve(args.c2_data)
    summary_path = resolve(args.c2_summary)
    business_path = resolve(args.c2_business_receipt)
    c2 = load_object(c2_path, "C2 data")
    summary = load_object(summary_path, "C2 homepage summary")
    business = load_object(business_path, "C2 business-success receipt")

    meta = dict(c2.get("meta") or {})
    v2 = dict(meta.get("v2") or {})
    release_tag = str(v2.get("c1_release_tag") or meta.get("official_shared_release_tag") or "")
    snapshot_sha = str(meta.get("official_shared_sha256") or "").removeprefix("sha256:").lower()
    daily_raw = meta.get("daily_target_end") or meta.get("official_shared_source_max_date")
    daily_target = date.fromisoformat(str(daily_raw)[:10]) if daily_raw else None

    source = dict(summary.get("source") or {})
    summary_tag = str(source.get("c1_release_tag") or "")
    summary_daily_raw = source.get("daily_data_through")
    summary_daily = date.fromisoformat(str(summary_daily_raw)[:10]) if summary_daily_raw else None
    summary_snapshot = str(source.get("c1_snapshot_sha256") or "").removeprefix("sha256:").lower()

    add_check(checks, "c1_release_pinned", bool(release_tag), f"c1_release_tag={release_tag}")
    add_check(checks, "c2_summary_release_matches", summary_tag == release_tag, f"summary={summary_tag}, data={release_tag}")
    add_check(checks, "c2_summary_daily_matches", summary_daily == daily_target, f"summary={summary_daily}, data={daily_target}")
    add_check(checks, "c2_summary_snapshot_matches", bool(snapshot_sha) and summary_snapshot == snapshot_sha, f"summary={summary_snapshot}, data={snapshot_sha}")
    add_check(checks, "c2_complete_through_month_end", daily_target is not None and daily_target >= end, f"daily_target={daily_target}, month_end={end}")
    add_check(checks, "c2_success_state_is_post_month_end", daily_target is not None and daily_target > end, f"daily_target={daily_target}, required_after={end}")

    data_sha = sha256_file(c2_path)
    summary_sha = sha256_file(summary_path)
    receipt_status = str(business.get("status") or "")
    receipt_commit = str(business.get("commit") or "")
    receipt_tag = str(business.get("c1_release_tag") or "")
    receipt_data_through_raw = business.get("data_through")
    receipt_data_through = date.fromisoformat(str(receipt_data_through_raw)[:10]) if receipt_data_through_raw else None
    receipt_snapshot = str(business.get("c1_snapshot_sha256") or "").removeprefix("sha256:").lower()
    receipt_bundle = str(business.get("c1_release_bundle_sha256") or "").removeprefix("sha256:").lower()

    add_check(checks, "c2_business_success_status", receipt_status == "business-success", f"status={receipt_status}")
    add_check(checks, "c2_business_release_matches", receipt_tag == release_tag, f"receipt={receipt_tag}, data={release_tag}")
    add_check(checks, "c2_business_data_through_matches", receipt_data_through == daily_target, f"receipt={receipt_data_through}, data={daily_target}")
    add_check(checks, "c2_business_snapshot_matches", bool(snapshot_sha) and receipt_snapshot == snapshot_sha and receipt_bundle == snapshot_sha, f"receipt_snapshot={receipt_snapshot}, bundle={receipt_bundle}, data={snapshot_sha}")
    add_check(checks, "c2_business_data_hash_matches", business.get("expected_data_sha256") == data_sha and business.get("pages_data_sha256") == data_sha, f"receipt_expected={business.get('expected_data_sha256')}, receipt_pages={business.get('pages_data_sha256')}, current={data_sha}")
    add_check(checks, "c2_business_summary_hash_matches", business.get("expected_summary_sha256") == summary_sha and business.get("pages_summary_sha256") == summary_sha, f"receipt_expected={business.get('expected_summary_sha256')}, receipt_pages={business.get('pages_summary_sha256')}, current={summary_sha}")
    if args.expected_c2_commit:
        add_check(checks, "c2_business_commit_matches", receipt_commit == args.expected_c2_commit, f"receipt={receipt_commit}, expected={args.expected_c2_commit}")
    else:
        add_check(checks, "c2_business_commit_present", len(receipt_commit) == 40, f"receipt={receipt_commit}")

    geo_path = resolve(args.geography)
    geo = pd.read_csv(geo_path, dtype=str).fillna("")
    required = {"station_id", "epci_siren", "epci_nom", "commune"}
    missing_cols = sorted(required.difference(geo.columns))
    add_check(checks, "geography_columns", not missing_cols, f"missing_columns={missing_cols}")
    duplicate_ids = [] if "station_id" not in geo.columns else sorted(geo.loc[geo["station_id"].duplicated(keep=False), "station_id"].unique())
    add_check(checks, "geography_unique_station_ids", not duplicate_ids, f"duplicate_station_ids={duplicate_ids[:10]}")
    if not missing_cols:
        incomplete = geo[(geo["station_id"].str.strip() == "") | (geo["commune"].str.strip() == "") | (geo["epci_siren"].str.strip() == "") | (geo["epci_nom"].str.strip() == "")]
        epci_count = int(geo["epci_siren"].nunique())
        add_check(checks, "geography_complete_rows", incomplete.empty, f"incomplete_rows={len(incomplete)}")
        add_check(checks, "geography_has_19_epci", epci_count == 19, f"epci_count={epci_count}, station_rows={len(geo)}")
    else:
        epci_count = None
        add_check(checks, "geography_complete_rows", False, "required columns missing")
        add_check(checks, "geography_has_19_epci", False, "required columns missing")

    receipt_dir = resolve(args.receipt_dir)
    receipt_path = receipt_dir / f"{month}.json"
    if receipt_path.exists():
        try:
            final_receipt = load_object(receipt_path, "monthly final receipt")
            receipt_valid = final_receipt.get("schema") == FINAL_RECEIPT_SCHEMA and final_receipt.get("status") == "final" and final_receipt.get("month") == month
            detail = f"schema={final_receipt.get('schema')}, status={final_receipt.get('status')}, month={final_receipt.get('month')}"
        except Exception as exc:
            receipt_valid = False
            detail = str(exc)
        add_check(checks, "existing_monthly_receipt_valid", receipt_valid, detail)
        add_check(checks, "month_not_already_finalized", False, f"receipt={receipt_path} exists")
    else:
        add_check(checks, "month_not_already_finalized", True, f"receipt={receipt_path} absent")

    ready = all(c["ok"] for c in checks)
    result = {
        "schema": "a4c-monthly-readiness-v2",
        "ready": ready,
        "month": month,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "as_of": as_of.isoformat(),
        "c2_daily_target_end": daily_target.isoformat() if daily_target else None,
        "c2_business_success_commit": receipt_commit,
        "c2_business_success_data_sha256": data_sha,
        "c2_business_success_summary_sha256": summary_sha,
        "c1_release_tag": release_tag,
        "c1_snapshot_sha256": snapshot_sha,
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
