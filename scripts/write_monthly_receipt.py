#!/usr/bin/env python3
"""Write one immutable, fail-closed final receipt for a completed monthly build."""
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
SOURCE_GUARD_SCHEMA = "a4c-monthly-source-guards-v3"
BROWSER_SCHEMA = "a4c-monthly-widget-browser-smoke-v3"
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    for name in ("month", "dataset", "readiness", "source-guards", "browser-smoke", "widget", "geography", "c2-business-receipt", "output"):
        p.add_argument(f"--{name}", required=True)
    return p.parse_args()


def period(month: str) -> tuple[str, str, str]:
    m = MONTH_RE.fullmatch(month)
    if not m:
        raise RuntimeError("month must be canonical YYYY-MM")
    y, mo = int(m.group(1)), int(m.group(2))
    start = date(y, mo, 1)
    end = date(y, mo, calendar.monthrange(y, mo)[1])
    prev_start = (start - timedelta(days=1)).replace(day=1)
    return start.isoformat(), end.isoformat(), prev_start.isoformat()


def evidence(path: Path, label: str) -> tuple[dict, str]:
    try:
        raw = path.read_bytes()
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(obj, dict):
        raise RuntimeError(f"{label} root is not an object")
    return obj, hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def obj(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def arr(value, label: str) -> list:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def text(d: dict, key: str, label: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label}.{key} is required")
    return value.strip()


def sha(d: dict, key: str, label: str) -> str:
    value = text(d, key, label).lower().removeprefix("sha256:")
    if not SHA_RE.fullmatch(value):
        raise RuntimeError(f"{label}.{key} is not a SHA-256")
    return value


def commit(d: dict, key: str, label: str) -> str:
    value = text(d, key, label).lower()
    if not COMMIT_RE.fullmatch(value):
        raise RuntimeError(f"{label}.{key} is not a full commit SHA")
    return value


def same(actual, expected, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: {actual!r} != {expected!r}")


def main() -> None:
    a = parse_args()
    start, end, prev_start = period(a.month)
    paths = {
        "dataset": Path(a.dataset), "readiness": Path(a.readiness),
        "guards": Path(a.source_guards), "browser": Path(a.browser_smoke),
        "widget": Path(a.widget), "geography": Path(a.geography),
        "business": Path(a.c2_business_receipt),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing {label}: {path}")

    dataset, dataset_sha = evidence(paths["dataset"], "dataset")
    readiness, readiness_sha = evidence(paths["readiness"], "readiness")
    guards, guards_sha = evidence(paths["guards"], "source guards")
    browser, browser_sha = evidence(paths["browser"], "browser smoke")
    business, _ = evidence(paths["business"], "C2 business-success receipt")

    meta = obj(dataset.get("meta"), "dataset.meta")
    same(meta.get("schema"), DATASET_SCHEMA, "dataset schema")
    same(text(meta, "month", "dataset.meta"), a.month, "dataset month")
    same(text(meta, "period_start", "dataset.meta"), start, "dataset period_start")
    same(text(meta, "period_end", "dataset.meta"), end, "dataset period_end")
    tag = text(meta, "c1_release_tag", "dataset.meta")
    c2_main = commit(meta, "c2_main_sha_runtime", "dataset.meta")
    engine = text(meta, "c2_engine", "dataset.meta")
    geo_rows = meta.get("geography_rows")
    epci_count = meta.get("epci_count_registry")
    if not isinstance(geo_rows, int) or geo_rows <= 0 or epci_count != 19:
        raise RuntimeError("dataset geography provenance is incomplete")

    same(readiness.get("schema"), READINESS_SCHEMA, "readiness schema")
    same(readiness.get("month"), a.month, "readiness month")
    same(readiness.get("period_start"), start, "readiness period_start")
    same(readiness.get("period_end"), end, "readiness period_end")
    if readiness.get("ready") is not True:
        raise RuntimeError("readiness does not prove this month ready")
    same(text(readiness, "c1_release_tag", "readiness"), tag, "readiness C1 release")
    ready_commit = commit(readiness, "c2_business_success_commit", "readiness")
    ready_data_sha = sha(readiness, "c2_business_success_data_sha256", "readiness")
    ready_summary_sha = sha(readiness, "c2_business_success_summary_sha256", "readiness")
    checks = arr(readiness.get("checks"), "readiness.checks")
    if not checks or any(not isinstance(x, dict) or x.get("ok") is not True for x in checks):
        raise RuntimeError("readiness checks are missing or not all successful")

    same(guards.get("schema"), SOURCE_GUARD_SCHEMA, "source guard schema")
    same(guards.get("month"), a.month, "source guard month")
    same(guards.get("period_start"), start, "source guard period_start")
    same(guards.get("period_end"), end, "source guard period_end")
    same(guards.get("guard_period_start"), prev_start, "source guard reconstruction start")
    same(guards.get("guard_period_end"), end, "source guard reconstruction end")
    same(text(guards, "c1_release_tag", "source guards"), tag, "source guard C1 release")
    if guards.get("status") != "pass":
        raise RuntimeError("source guards did not pass")
    for key in ("missing_geography", "unknown_recent_bdr_stations", "unknown_bdr_details"):
        if arr(guards.get(key), f"source_guards.{key}"):
            raise RuntimeError(f"source guards contain {key}")

    guard_backfill = obj(guards.get("bdr_category_backfill"), "source guard backfill")
    policy = obj(guard_backfill.get("policy"), "source guard backfill policy")
    expected_policy = {
        "scope": "monthly_reconstruction_only",
        "same_station_id_required": True,
        "max_backfill_days": 7,
        "verified_future_category_required": True,
        "contradictory_brand_or_category_blocks": True,
        "price_or_eligibility_modified": False,
        "window_start": prev_start,
        "window_end": end,
    }
    for key, expected in expected_policy.items():
        same(policy.get(key), expected, f"backfill policy {key}")
    arr(guard_backfill.get("applied_ranges"), "source guard applied_ranges")
    if arr(guard_backfill.get("rejected_conflicts"), "source guard rejected_conflicts"):
        raise RuntimeError("source guard backfill contains conflicts")

    dataset_backfill = obj(obj(dataset.get("internal_audit"), "dataset.internal_audit").get("bdr_category_backfill"), "dataset backfill")
    for key in ("policy", "applied_station_days", "applied_network_station_days", "applied_gms_station_days", "applied_ranges", "rejected_conflicts"):
        same(dataset_backfill.get(key), guard_backfill.get(key), f"dataset/source-guard backfill {key}")

    same(browser.get("schema"), BROWSER_SCHEMA, "browser schema")
    if browser.get("ok") is not True:
        raise RuntimeError("browser smoke did not pass")
    same(text(browser, "dataset_month", "browser smoke"), a.month, "browser dataset month")
    browser_dataset_sha = sha(browser, "dataset_sha256", "browser smoke")
    same(browser_dataset_sha, dataset_sha, "browser-tested dataset hash")
    tests = obj(browser.get("tests"), "browser tests")
    for mode in ("desktop", "mobile"):
        result = obj(tests.get(mode), f"browser {mode}")
        if result.get("ok") is not True:
            raise RuntimeError(f"browser {mode} did not pass")
        same(result.get("datasetSha256"), dataset_sha, f"browser {mode} dataset hash")
        same(result.get("datasetMonth"), a.month, f"browser {mode} dataset month")

    if business.get("status") != "business-success":
        raise RuntimeError("C2 receipt is not business-success")
    business_commit = commit(business, "commit", "C2 business receipt")
    business_tag = text(business, "c1_release_tag", "C2 business receipt")
    business_data = sha(business, "expected_data_sha256", "C2 business receipt")
    pages_data = sha(business, "pages_data_sha256", "C2 business receipt")
    business_summary = sha(business, "expected_summary_sha256", "C2 business receipt")
    pages_summary = sha(business, "pages_summary_sha256", "C2 business receipt")
    data_through = text(business, "data_through", "C2 business receipt")
    same(business_tag, tag, "dataset/C2 business C1 release")
    same(ready_commit, business_commit, "readiness/C2 business commit")
    same(ready_data_sha, business_data, "readiness/C2 business data hash")
    same(pages_data, business_data, "C2 repository/Pages data hash")
    same(ready_summary_sha, business_summary, "readiness/C2 business summary hash")
    same(pages_summary, business_summary, "C2 repository/Pages summary hash")

    receipt = {
        "schema": SCHEMA, "status": "final", "month": a.month,
        "period_start": start, "period_end": end,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "c1_release_tag": tag,
        "c2_main_commit_at_monthly_run": c2_main,
        "c2_business_receipt_commit": business_commit,
        "c2_data_through": data_through,
        "c2_expected_data_sha256": business_data,
        "c2_pages_data_sha256": pages_data,
        "c2_expected_summary_sha256": business_summary,
        "c2_pages_summary_sha256": pages_summary,
        "dataset_sha256": dataset_sha,
        "readiness_sha256": readiness_sha,
        "source_guards_sha256": guards_sha,
        "browser_smoke_sha256": browser_sha,
        "browser_dataset_sha256": browser_dataset_sha,
        "widget_sha256": file_sha(paths["widget"]),
        "geography_sha256": file_sha(paths["geography"]),
        "provenance": {
            "dataset_schema": DATASET_SCHEMA, "c2_engine": engine,
            "geography_rows": geo_rows, "epci_count": epci_count,
            "source_guard_schema": SOURCE_GUARD_SCHEMA, "browser_schema": BROWSER_SCHEMA,
        },
    }

    out = Path(a.output)
    if out.name != f"{a.month}.json":
        raise RuntimeError(f"receipt output filename must be exactly {a.month}.json")
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
