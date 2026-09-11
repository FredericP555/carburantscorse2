#!/usr/bin/env python3
"""Write one immutable final receipt for a completed monthly territorial build.

The writer is deliberately atomic on the local filesystem (O_EXCL) and refuses to overwrite or
silently accept an existing receipt. Cross-run serialization must additionally be provided by the
GitHub Actions workflow concurrency group.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

SCHEMA = "a4c-monthly-final-receipt-v1"


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


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} root is not an object")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    args = parse_args()
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

    dataset = load(paths["dataset"], "dataset")
    readiness = load(paths["readiness"], "readiness")
    source_guards = load(paths["source_guards"], "source guards")
    browser = load(paths["browser_smoke"], "browser smoke")
    business = load(paths["c2_business_receipt"], "C2 business-success receipt")

    if dataset.get("meta", {}).get("month") != args.month:
        raise RuntimeError("dataset month does not match requested month")
    if readiness.get("month") != args.month or readiness.get("ready") is not True:
        raise RuntimeError("readiness does not prove this month ready")
    if source_guards.get("month") != args.month or source_guards.get("status") != "pass":
        raise RuntimeError("source guards do not prove this month safe")
    if source_guards.get("missing_geography"):
        raise RuntimeError("source guards contain missing geography")
    if source_guards.get("unknown_recent_bdr_stations"):
        raise RuntimeError("source guards contain unknown recent BDR stations")
    if browser.get("ok") is not True:
        raise RuntimeError("browser smoke is not successful")
    if business.get("status") != "business-success":
        raise RuntimeError("C2 receipt is not business-success")

    meta = dataset.get("meta") or {}
    if meta.get("c1_release_tag") != business.get("c1_release_tag"):
        raise RuntimeError("dataset and C2 receipt use different C1 releases")
    if readiness.get("c2_business_success_commit") != business.get("commit"):
        raise RuntimeError("readiness and C2 receipt commit differ")
    if readiness.get("c2_business_success_data_sha256") != business.get("expected_data_sha256"):
        raise RuntimeError("readiness and C2 receipt data hash differ")

    receipt = {
        "schema": SCHEMA,
        "status": "final",
        "month": args.month,
        "period_start": meta.get("period_start"),
        "period_end": meta.get("period_end"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "c1_release_tag": meta.get("c1_release_tag"),
        "c2_main_commit_at_monthly_run": meta.get("c2_main_sha_runtime"),
        "c2_business_receipt_commit": business.get("commit"),
        "c2_data_through": business.get("data_through"),
        "c2_expected_data_sha256": business.get("expected_data_sha256"),
        "c2_pages_data_sha256": business.get("pages_data_sha256"),
        "dataset_sha256": sha256(paths["dataset"]),
        "readiness_sha256": sha256(paths["readiness"]),
        "source_guards_sha256": sha256(paths["source_guards"]),
        "browser_smoke_sha256": sha256(paths["browser_smoke"]),
        "widget_sha256": sha256(paths["widget"]),
        "geography_sha256": sha256(paths["geography"]),
        "provenance": {
            "dataset_schema": meta.get("schema"),
            "c2_engine": meta.get("c2_engine"),
            "geography_rows": meta.get("geography_rows"),
            "epci_count": meta.get("epci_count_registry"),
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise RuntimeError(f"monthly receipt already exists; refusing overwrite: {out}") from exc
    with os.fdopen(fd, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
