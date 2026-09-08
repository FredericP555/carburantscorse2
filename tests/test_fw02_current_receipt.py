from __future__ import annotations

import json
import unittest

from scripts import validate_current_c2_receipt as current
from scripts import verify_c2_business_success as business


def data(marker: int = 1) -> bytes:
    return json.dumps({"meta": {"daily_target_end": "2026-09-07", "weekly_complete_through": "2026-09-06", "official_shared_release_tag": "tag", "official_shared_sha256": "a" * 64, "v2": {"c1_release_tag": "tag"}}, "marker": marker}, separators=(",", ":")).encode()


def summary(marker: int = 1) -> bytes:
    return json.dumps({"schema": "a4c-homepage-summary-v1", "source": {"c1_release_tag": "tag", "c1_snapshot_sha256": "a" * 64, "daily_data_through": "2026-09-07", "weekly_data_through": "2026-09-06"}, "marker": marker}, separators=(",", ":")).encode()


def receipt(d: bytes, s: bytes) -> dict:
    return {
        "status": "business-success",
        "c1_release_tag": "tag",
        "c1_snapshot_sha256": "a" * 64,
        "c1_release_bundle_sha256": "a" * 64,
        "expected_data_sha256": business.sha256_bytes(d),
        "pages_data_sha256": business.sha256_bytes(d),
        "expected_summary_sha256": business.sha256_bytes(s),
        "pages_summary_sha256": business.sha256_bytes(s),
    }


class FW02CurrentReceiptTests(unittest.TestCase):
    def test_current_repo_and_pages_match_receipt(self):
        d, s = data(), summary()
        current.validate_current_receipt(receipt(d, s), expected_tag="tag", current_data=d, current_summary=s, pages_data=d, pages_summary=s)

    def test_old_receipt_rejected_after_repository_data_changes(self):
        old_d, s = data(1), summary()
        with self.assertRaises(ValueError):
            current.validate_current_receipt(receipt(old_d, s), expected_tag="tag", current_data=data(2), current_summary=s, pages_data=data(2), pages_summary=s)

    def test_old_receipt_rejected_after_repository_summary_changes(self):
        d, old_s = data(), summary(1)
        with self.assertRaises(ValueError):
            current.validate_current_receipt(receipt(d, old_s), expected_tag="tag", current_data=d, current_summary=summary(2), pages_data=d, pages_summary=summary(2))

    def test_receipt_rejected_if_pages_no_longer_match_current_repo(self):
        d, s = data(), summary()
        with self.assertRaises(ValueError):
            current.validate_current_receipt(receipt(d, s), expected_tag="tag", current_data=d, current_summary=s, pages_data=data(2), pages_summary=s)


if __name__ == "__main__":
    unittest.main()
