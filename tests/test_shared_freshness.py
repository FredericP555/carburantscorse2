from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.check_shared_freshness import evaluate_shared_freshness


NOW = datetime(2026, 8, 24, 5, 40, tzinfo=timezone.utc)  # 07:40 Europe/Paris


def candidate(*, release_at="2026-08-24T05:15:00Z", source_max="2026-08-23", by_fuel=None):
    if by_fuel is None:
        by_fuel = {"Gazole": source_max, "SP95": source_max, "E10": source_max}
    return {
        "official_ingestion_source": "c1-github-release",
        "official_shared_release_tag": "a4c-shared-test",
        "official_shared_release_published_at": release_at,
        "official_shared_source_max_date": source_max,
        "official_shared_source_max_date_by_fuel": by_fuel,
    }


def baseline(source_max="2026-08-18", by_fuel=None):
    if by_fuel is None:
        by_fuel = {"Gazole": source_max, "SP95": source_max, "E10": source_max}
    return {
        "official_shared_source_max_date": source_max,
        "official_shared_source_max_date_by_fuel": by_fuel,
    }


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

    def test_release_timestamp_can_be_recovered_from_current_tag_format(self):
        current = candidate(release_at=None)
        current["official_shared_release_tag"] = "a4c-shared-20260824T051500Z-123456"
        report = self.evaluate(current, baseline())
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["release_timestamp_source"], "release-tag")
        self.assertEqual(report["release_published_at"], "2026-08-24T05:15:00Z")

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

    def test_stale_sp95_fails_even_when_global_max_and_gazole_are_fresh(self):
        report = self.evaluate(
            candidate(
                source_max="2026-08-23",
                by_fuel={"Gazole": "2026-08-23", "SP95": "2026-08-18", "E10": "2026-08-23"},
            ),
            baseline("2026-08-17"),
        )
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("SP95" in item and "stale" in item for item in report["failures"]))

    def test_required_per_fuel_dates_must_be_present(self):
        current = candidate()
        current.pop("official_shared_source_max_date_by_fuel")
        report = self.evaluate(current, baseline())
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("per-fuel" in item for item in report["failures"]))

    def test_per_fuel_regression_fails_even_if_global_stock_advances(self):
        report = self.evaluate(
            candidate(
                source_max="2026-08-23",
                by_fuel={"Gazole": "2026-08-23", "SP95": "2026-08-22", "E10": "2026-08-23"},
            ),
            baseline(
                "2026-08-22",
                by_fuel={"Gazole": "2026-08-22", "SP95": "2026-08-23", "E10": "2026-08-22"},
            ),
        )
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("SP95" in item and "regressed" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
