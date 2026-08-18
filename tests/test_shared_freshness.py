from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.check_shared_freshness import evaluate_shared_freshness


NOW = datetime(2026, 8, 24, 5, 40, tzinfo=timezone.utc)  # 07:40 Europe/Paris


def candidate(*, release_at="2026-08-24T05:15:00Z", source_max="2026-08-23"):
    return {
        "official_ingestion_source": "c1-github-release",
        "official_shared_release_tag": "a4c-shared-test",
        "official_shared_release_published_at": release_at,
        "official_shared_source_max_date": source_max,
    }


def baseline(source_max="2026-08-18"):
    return {"official_shared_source_max_date": source_max}


class SharedFreshnessTests(unittest.TestCase):
    def evaluate(self, current, previous):
        return evaluate_shared_freshness(
            current,
            previous,
            now=NOW,
            max_release_age_hours=12,
            max_source_age_days=4,
        )

    def test_fresh_release_and_advanced_stock_pass(self):
        report = self.evaluate(candidate(), baseline())
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["source_progression"], "advanced")
        self.assertEqual(report["failures"], [])

    def test_fresh_release_with_unchanged_but_recent_stock_is_explicit_noop(self):
        report = self.evaluate(candidate(source_max="2026-08-23"), baseline("2026-08-23"))
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["source_progression"], "unchanged")
        self.assertTrue(any("did not advance" in item for item in report["warnings"]))

    def test_old_release_fails_even_if_stock_date_is_recent(self):
        report = self.evaluate(candidate(release_at="2026-08-17T05:15:00Z"), baseline())
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("Release is stale" in item for item in report["failures"]))

    def test_fresh_release_with_frozen_official_stock_fails_as_data_staleness(self):
        report = self.evaluate(candidate(source_max="2026-08-18"), baseline("2026-08-18"))
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["source_progression"], "unchanged")
        self.assertTrue(any("official stock is stale" in item for item in report["failures"]))

    def test_regressed_stock_fails(self):
        report = self.evaluate(candidate(source_max="2026-08-22"), baseline("2026-08-23"))
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["source_progression"], "regressed")
        self.assertTrue(any("regressed" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
