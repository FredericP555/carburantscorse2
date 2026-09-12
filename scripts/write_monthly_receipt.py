#!/usr/bin/env python3
"""Write one immutable final receipt for a completed monthly territorial build.

The writer is fail-closed: every evidence document must be complete, internally coherent and tied
to the requested month. The browser evidence must identify the exact dataset bytes it exercised.
The final receipt is published atomically with a no-clobber hard link, so an interrupted write
cannot leave a partial final receipt and two writers cannot both finalize the same month on one
filesystem. Cross-run serialization must additionally be provided by the future workflow.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re

SCHEMA = "a4c-monthly-final-receipt-v1"
DATASET_SCHEMA = "a4c-monthly-territories-v2-c2-engine"
READINESS_SCHEMA = "a4c-monthly-readiness-v2"
SOURCE_GUARD_SCHEMA = "a4c-monthly-source-guards-v4"
BROWSER_SCHEMA = "a4c-monthly-widget-browser-smoke-v3"
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--readiness", required=True)
    p.add_argument("--source-guards", required=True)
    p.add_argument("--browser-smoke", required=True)
    p.add_argument("--widget", required=True)
    p.add_argument("--geography", required=True)
    p.add_argument("--c2-business-receipt", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def month_period(month: str) -> tuple[str, str, str]:
    match = MONTH_RE.fullmatch(month)
    if not match:
        raise RuntimeError("month must be canonical YYYY-MM")
    year, mon = int(match.group(1)), int(match.group(2))
    start = date(year, mon, 1)
    end = date(year, mon, calendar.monthrange(year, mon)[1])
    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    return start.isoformat(), end.isoformat(), previous_start.isoformat()


def read_json_evidence(path: Path, label: str) -> tuple[dict, bytes, str]:
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise RuntimeError(f"cannot read {label}: {path}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} root is not an object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def require_list(value, label: str) -> list:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def require_text(obj: dict, key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label}.{key} is required")
    return value.strip()


def require_sha(obj: dict, key: str, label: str) -> str:
    value = require_text(obj, key, label).lower().removeprefix("sha256:")
    if not SHA256_RE.fullmatch(value):
        raise RuntimeError(f"{label}.{key} is not a SHA-256")
    return value


def require_commit(obj: dict, key: str, label: str) -> str:
    value = require_text(obj, key, label).lower()
    if not COMMIT_RE.fullmatch(value):
        raise RuntimeError(f"{label}.{key} is not a full 40-char commit SHA")
    return value


def require_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: {actual!r} != {expected!r}")


def main() -> None:
    args = parse_args()
    period_start, period_end, previous_period_start = month_period(args.month)
    paths = {
        "dataset": Path(args.dataset),
        "readiness": Path(args.readiness),
        "source_guards": Path(args.source_guards),
        "browser_smoke": Path(args.browser_smoke),
        "widget": Path(args.widget),
        "geography": Path(args.geography),
        "c2_business_receipt": Path(args.c2_business_receipt),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing {label}: {path}")

    dataset, _dataset_raw, dataset_sha = read_json_evidence(paths["dataset"], "dataset")
    readiness, _readiness_raw, readiness_sha = read_json_evidence(paths["readiness"], "readiness")
    source_guards, _guards_raw, source_guards_sha = read_json_evidence(paths["source_guards"], "source guards")
    browser, _browser_raw, browser_sha = read_json_evidence(paths["browser_smoke"], "browser smoke")
    business, _business_raw, _business_sha = read_json_evidence(paths["c2_business_receipt"], "C2 business-success receipt")

    meta = require_object(dataset.get("meta"), "dataset.meta")
    require_equal(meta.get("schema"), DATASET_SCHEMA, "dataset schema")
    require_equal(require_text(meta, "month", "dataset.meta"), args.month, "dataset month")
    require_equal(require_text(meta, "period_start", "dataset.meta"), period_start, "dataset period_start")
    require_equal(require_text(meta, "period_end", "dataset.meta"), period_end, "dataset period_end")
    dataset_tag = require_text(meta, "c1_release_tag", "dataset.meta")
    dataset_c2_main = require_commit(meta, "c2_main_sha_runtime", "dataset.meta")
    dataset_engine = require_text(meta, "c2_engine", "dataset.meta")
    geography_rows = meta.get("geography_rows")
    epci_count = meta.get("epci_count_registry")
    if not isinstance(geography_rows, int) or geography_rows <= 0:
        raise RuntimeError("dataset.meta.geography_rows must be a positive integer")
    if epci_count != 19:
        raise RuntimeError("dataset.meta.epci_count_registry must equal 19")

    require_equal(readiness.get("schema"), READINESS_SCHEMA, "readiness schema")
    require_equal(readiness.get("month"), args.month, "readiness month")
    require_equal(readiness.get("period_start"), period_start, "readiness period_start")
    require_equal(readiness.get("period_end"), period_end, "readiness period_end")
    if readiness.get("ready") is not True:
        raise RuntimeError("readiness does not prove this month ready")
    require_equal(require_text(readiness, "c1_release_tag", "readiness"), dataset_tag, "readiness C1 release")
    readiness_commit = require_commit(readiness, "c2_business_success_commit", "readiness")
    readiness_data_sha = require_sha(readiness, "c2_business_success_data_sha256", "readiness")
    readiness_summary_sha = require_sha(readiness, "c2_business_success_summary_sha256", "readiness")
    checks = require_list(readiness.get("checks"), "readiness.checks")
    if not checks or any(not isinstance(check, dict) or check.get("ok") is not True for check in checks):
        raise RuntimeError("readiness checks are missing or contain a failed/incomplete check")

    require_equal(source_guards.get("schema"), SOURCE_GUARD_SCHEMA, "source guard schema")
    require_equal(source_guards.get("month"), args.month, "source guard month")
    require_equal(source_guards.get("period_start"), period_start, "source guard period_start")
    require_equal(source_guards.get("period_end"), period_end, "source guard period_end")
    require_equal(source_guards.get("guard_period_start"), previous_period_start, "source guard reconstruction start")
    require_equal(source_guards.get("guard_period_end"), period_end, "source guard reconstruction end")
    require_equal(require_text(source_guards, "c1_release_tag", "source guards"), dataset_tag, "source guard C1 release")
    if source_guards.get("status") != "pass":
        raise RuntimeError("source guards do not prove this reconstruction window safe")
    for key in ("missing_geography", "unknown_recent_bdr_stations", "unknown_bdr_details"):
        values = require_list(source_guards.get(key), f"source_guards.{key}")
        if values:
            raise RuntimeError(f"source guards contain {key}")

    source_backfill = require_object(source_guards.get("bdr_category_backfill"), "source_guards.bdr_category_backfill")
    policy = require_object(source_backfill.get("policy"), "source_guards.bdr_category_backfill.policy")
    require_equal(policy.get("scope"), "monthly_reconstruction_only", "backfill policy scope")
    if policy.get("same_station_id_required") is not True:
        raise RuntimeError("backfill policy must require the same station_id")
    if policy.get("max_backfill_days") != 7:
        raise RuntimeError("backfill policy must be limited to 7 days")
    if policy.get("verified_future_category_required") is not True:
        raise RuntimeError("backfill policy must require a verified future category")
    if policy.get("contradictory_brand_or_category_blocks") is not True:
        raise RuntimeError("backfill policy must block contradictory evidence")
    if policy.get("price_or_eligibility_modified") is not False:
        raise RuntimeError("backfill policy must not modify price or eligibility")
    require_equal(policy.get("window_start"), previous_period_start, "backfill policy window_start")
    require_equal(policy.get("window_end"), period_end, "backfill policy window_end")
    require_list(source_backfill.get("applied_ranges"), "source_guards.bdr_category_backfill.applied_ranges")
    rejected = require_list(source_backfill.get("rejected_conflicts"), "source_guards.bdr_category_backfill.rejected_conflicts")
    if rejected:
        raise RuntimeError("source guard backfill contains rejected conflicts")

    dataset_internal = require_object(dataset.get("internal_audit"), "dataset.internal_audit")
    dataset_backfill = require_object(dataset_internal.get("bdr_category_backfill"), "dataset.internal_audit.bdr_category_backfill")
    for key in ("policy", "applied_station_days", "applied_network_station_days", "applied_gms_station_days", "applied_ranges", "rejected_conflicts"):
        require_equal(dataset_backfill.get(key), source_backfill.get(key), f"dataset/source-guard backfill evidence {key}")

    require_equal(browser.get("schema"), BROWSER_SCHEMA, "browser smoke schema")
    if browser.get("ok") is not True:
        raise RuntimeError("browser smoke is not successful")
    require_equal(require_text(browser, "dataset_month", "browser smoke"), args.month, "browser dataset month")
    browser_dataset_sha = require_sha(browser, "dataset_sha256", "browser smoke")
    require_equal(browser_dataset_sha, dataset_sha, "browser-tested dataset SHA-256")
    tests = require_object(browser.get("tests"), "browser smoke.tests")
    for mode in ("desktop", "mobile"):
        mode_result = require_object(tests.get(mode), f"browser smoke.tests.{mode}")
        if mode_result.get("ok") is not True:
            raise RuntimeError(f"browser smoke {mode} evidence is not successful")
        require_equal(mode_result.get("datasetSha256"), dataset_sha, f"browser smoke {mode} dataset SHA-256")
        require_equal(mode_result.get("datasetMonth"), args.month, f"browser smoke {mode} dataset month")

    if business.get("status") != "business-success":
        raise RuntimeError("C2 receipt is not business-success")
    business_commit = require_commit(business, "commit", "C2 business-success receipt")
    business_tag = require_text(business, "c1_release_tag", "C2 business-success receipt")
    business_data_sha = require_sha(business, "expected_data_sha256", "C2 business-success receipt")
    business_pages_data_sha = require_sha(business, "pages_data_sha256", "C2 business-success receipt")
    business_summary_sha = require_sha(business, "expected_summary_sha256", "C2 business-success receipt")
    business_pages_summary_sha = require_sha(business, "pages_summary_sha256", "C2 business-success receipt")
    data_through = require_text(business, "data_through", "C2 business-success receipt")

    require_equal(business_tag, dataset_tag, "dataset/C2 business C1 release")
    require_equal(readiness_commit, business_commit, "readiness/C2 business commit")
    require_equal(readiness_data_sha, business_data_sha, "readiness/C2 business data hash")
    require_equal(business_pages_data_sha, business_data_sha, "C2 repository/Pages data hash")
    require_equal(readiness_summary_sha, business_summary_sha, "readiness/C2 business summary hash")
    require_equal(business_pages_summary_sha, business_summary_sha, "C2 repository/Pages summary hash")

    receipt = {
        "schema": SCHEMA,
        "status": "final",
        "month": args.month,
        "period_start": period_start,
        "period_end": period_end,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "c1_release_tag": dataset_tag,
        "c2_main_commit_at_monthly_run": dataset_c2_main,
        "c2_business_receipt_commit": business_commit,
        "c2_data_through": data_through,
        "c2_expected_data_sha256": business_data_sha,
        "c2_pages_data_sha256": business_pages_data_sha,
        "c2_expected_summary_sha256": business_summary_sha,
        "c2_pages_summary_sha256": business_pages_summary_sha,
        "dataset_sha256": dataset_sha,
        "readiness_sha256": readiness_sha,
        "source_guards_sha256": source_guards_sha,
        "browser_smoke_sha256": browser_sha,
        "browser_dataset_sha256": browser_dataset_sha,
        "widget_sha256": sha256_file(paths["widget"]),
        "geography_sha256": sha256_file(paths["geography"]),
        "provenance": {
            "dataset_schema": DATASET_SCHEMA,
            "c2_engine": dataset_engine,
            "geography_rows": geography_rows,
            "epci_count": epci_count,
            "source_guard_schema": SOURCE_GUARD_SCHEMA,
            "browser_schema": BROWSER_SCHEMA,
        },
    }

    out = Path(args.output)
    if out.name != f"{args.month}.json":
        raise RuntimeError(f"receipt output filename must be exactly {args.month}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise RuntimeError(f"monthly receipt already exists; refusing overwrite: {out}")

    payload = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(temp, out)
        except FileExistsError as exc:
            raise RuntimeError(f"monthly receipt already exists; refusing overwrite: {out}") from exc
        dir_fd = os.open(out.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass

    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
