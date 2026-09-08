#!/usr/bin/env python3
"""Accept a prior C2 business-success receipt only if it still proves current content."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

try:
    from scripts import verify_c2_business_success as business
except ImportError:  # direct execution as python scripts/validate_current_c2_receipt.py
    import verify_c2_business_success as business


def validate_current_receipt(
    receipt: dict,
    *,
    expected_tag: str,
    current_data: bytes,
    current_summary: bytes,
    pages_data: bytes,
    pages_summary: bytes,
) -> None:
    if receipt.get("status") != "business-success":
        raise ValueError("receipt status is not business-success")
    if receipt.get("c1_release_tag") != expected_tag:
        raise ValueError("receipt C1 tag does not match expected release")
    if receipt.get("c1_snapshot_sha256") != receipt.get("c1_release_bundle_sha256"):
        raise ValueError("receipt C1 snapshot/release digest mismatch")

    current_data_sha = business.sha256_bytes(current_data)
    current_summary_sha = business.sha256_bytes(current_summary)
    pages_data_sha = business.sha256_bytes(pages_data)
    pages_summary_sha = business.sha256_bytes(pages_summary)

    if receipt.get("expected_data_sha256") != current_data_sha:
        raise ValueError("receipt expected data hash no longer matches current repository data.json")
    if receipt.get("expected_summary_sha256") != current_summary_sha:
        raise ValueError("receipt expected summary hash no longer matches current repository summary")
    if receipt.get("pages_data_sha256") != current_data_sha:
        raise ValueError("receipt-certified Pages data hash differs from current repository data.json")
    if receipt.get("pages_summary_sha256") != current_summary_sha:
        raise ValueError("receipt-certified Pages summary hash differs from current repository summary")
    if pages_data_sha != current_data_sha:
        raise ValueError("currently served Pages data.json differs from current repository data.json")
    if pages_summary_sha != current_summary_sha:
        raise ValueError("currently served Pages summary differs from current repository summary")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", required=True)
    p.add_argument("--expected-tag", required=True)
    p.add_argument("--current-data", default="data.json")
    p.add_argument("--current-summary", default="homepage-summary.json")
    p.add_argument("--pages-data-file")
    p.add_argument("--pages-summary-file")
    p.add_argument("--data-url", default=business.DEFAULT_DATA_URL)
    p.add_argument("--summary-url", default=business.DEFAULT_SUMMARY_URL)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    current_data = Path(args.current_data).read_bytes()
    current_summary = Path(args.current_summary).read_bytes()
    if bool(args.pages_data_file) != bool(args.pages_summary_file):
        raise ValueError("both --pages-data-file and --pages-summary-file are required together")
    if args.pages_data_file:
        pages_data = Path(args.pages_data_file).read_bytes()
        pages_summary = Path(args.pages_summary_file).read_bytes()
    else:
        stamp = int(time.time() * 1000)
        pages_data, pages_summary = business.fetch_pair(
            business._cache_bust(args.data_url, stamp),
            business._cache_bust(args.summary_url, stamp),
        )
    validate_current_receipt(
        receipt,
        expected_tag=args.expected_tag,
        current_data=current_data,
        current_summary=current_summary,
        pages_data=pages_data,
        pages_summary=pages_summary,
    )
    print("C2 business-success receipt still matches current repository and Pages content")


if __name__ == "__main__":
    main()
