"""Tests-first contract for C2 end-to-end business success."""
from __future__ import annotations

import json
import unittest

from scripts import verify_c2_business_success as business


def data_payload(
    tag="c1-tag",
    snap="a" * 64,
    through="2026-09-06",
    weekly_through=None,
    marker=1,
) -> bytes:
    weekly_through = through if weekly_through is None else weekly_through
    return json.dumps({
        "meta": {
            "daily_target_end": through,
            "weekly_complete_through": weekly_through,
            "official_shared_release_tag": tag,
            "official_shared_sha256": snap,
            "v2": {"c1_release_tag": tag},
        },
        "marker": marker,
    }, separators=(",", ":")).encode()


def summary_payload(
    tag="c1-tag",
    snap="a" * 64,
    through="2026-09-06",
    weekly_through=None,
    marker=1,
) -> bytes:
    weekly_through = through if weekly_through is None else weekly_through
    return json.dumps({
        "schema": "a4c-homepage-summary-v1",
        "source": {
            "c1_release_tag": tag,
            "c1_snapshot_sha256": snap,
            "daily_data_through": through,
            "weekly_data_through": weekly_through,
        },
        "marker": marker,
    }, separators=(",", ":")).encode()


class C2BusinessSuccessTests(unittest.TestCase):
    def test_exact_pages_and_c1_release_link_pass(self):
        data = data_payload()
        summary = summary_payload()
        receipt = business.evaluate_publication(
            data, summary, data, summary,
            expected_commit="c2commit",
            data_url="https://example.test/data.json",
            summary_url="https://example.test/homepage-summary.json",
            c1_release_tag="c1-tag",
            c1_bundle_digest="sha256:" + "a" * 64,
        )
        self.assertEqual(receipt["status"], "business-success")
        self.assertEqual(receipt["c1_release_tag"], "c1-tag")
        self.assertEqual(receipt["c1_snapshot_sha256"], "a" * 64)
        self.assertEqual(receipt["data_through"], "2026-09-06")
        self.assertEqual(receipt["weekly_through"], "2026-09-06")
        self.assertEqual(receipt["expected_data_sha256"], receipt["pages_data_sha256"])
        self.assertEqual(receipt["expected_summary_sha256"], receipt["pages_summary_sha256"])

    def test_daily_may_be_ahead_of_last_complete_week(self):
        data = data_payload(through="2026-09-07", weekly_through="2026-09-06")
        summary = summary_payload(through="2026-09-07", weekly_through="2026-09-06")
        receipt = business.evaluate_publication(
            data, summary, data, summary,
            expected_commit="c2commit",
            data_url="d", summary_url="s",
            c1_release_tag="c1-tag",
            c1_bundle_digest="sha256:" + "a" * 64,
        )
        self.assertEqual(receipt["data_through"], "2026-09-07")
        self.assertEqual(receipt["weekly_through"], "2026-09-06")

    def test_weekly_cutoff_cannot_be_after_daily_cutoff(self):
        data = data_payload(through="2026-09-06", weekly_through="2026-09-07")
        summary = summary_payload(through="2026-09-06", weekly_through="2026-09-07")
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                data, summary, data, summary,
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="c1-tag", c1_bundle_digest="sha256:" + "a" * 64,
            )

    def test_stale_pages_data_fails(self):
        expected = data_payload(marker=2)
        stale = data_payload(through="2026-08-30", marker=1)
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                expected, summary_payload(), stale, summary_payload(),
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="c1-tag", c1_bundle_digest="sha256:" + "a" * 64,
            )

    def test_stale_pages_summary_fails(self):
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                data_payload(), summary_payload(marker=2), data_payload(), summary_payload(marker=1),
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="c1-tag", c1_bundle_digest="sha256:" + "a" * 64,
            )

    def test_local_data_and_summary_must_reference_same_c1_release(self):
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                data_payload(tag="A"), summary_payload(tag="B"),
                data_payload(tag="A"), summary_payload(tag="B"),
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="A", c1_bundle_digest="sha256:" + "a" * 64,
            )

    def test_expected_c1_release_tag_must_match_consumed_tag(self):
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                data_payload(tag="A"), summary_payload(tag="A"),
                data_payload(tag="A"), summary_payload(tag="A"),
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="B", c1_bundle_digest="sha256:" + "a" * 64,
            )

    def test_c1_bundle_digest_must_match_consumed_snapshot(self):
        with self.assertRaises(business.BusinessSuccessError):
            business.evaluate_publication(
                data_payload(), summary_payload(), data_payload(), summary_payload(),
                expected_commit="x", data_url="d", summary_url="s",
                c1_release_tag="c1-tag", c1_bundle_digest="sha256:" + "b" * 64,
            )


class C2BusinessPollingTests(unittest.TestCase):
    def test_poll_retries_stale_pair_then_passes(self):
        expected_data = data_payload(marker=2)
        expected_summary = summary_payload(marker=2)
        stale_data = data_payload(through="2026-08-30", marker=1)
        stale_summary = summary_payload(through="2026-08-30", marker=1)
        responses = iter([
            (stale_data, stale_summary),
            (expected_data, expected_summary),
        ])

        receipt = business.wait_for_publication(
            expected_data,
            expected_summary,
            data_url="d",
            summary_url="s",
            expected_commit="x",
            c1_release_tag="c1-tag",
            c1_bundle_digest="sha256:" + "a" * 64,
            timeout_seconds=30,
            interval_seconds=1,
            fetcher=lambda _d, _s: next(responses),
            sleeper=lambda _n: None,
        )
        self.assertEqual(receipt["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
