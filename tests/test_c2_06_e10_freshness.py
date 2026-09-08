from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.check_shared_freshness import evaluate_shared_freshness

NOW = datetime(2026, 8, 24, 5, 40, tzinfo=timezone.utc)


def candidate(by_fuel: dict[str, str]) -> dict:
    return {
        "official_ingestion_source": "c1-github-release",
        "official_shared_release_tag": "a4c-shared-test",
        "official_shared_release_published_at": "2026-08-24T05:15:00Z",
        "official_shared_source_max_date": "2026-08-23",
        "official_shared_source_max_date_by_fuel": by_fuel,
    }


def baseline(by_fuel: dict[str, str]) -> dict:
    return {
        "official_shared_source_max_date": "2026-08-22",
        "official_shared_source_max_date_by_fuel": by_fuel,
    }


class C206E10FreshnessTests(unittest.TestCase):
    def evaluate(self, current: dict, previous: dict) -> dict:
        return evaluate_shared_freshness(
            current,
            previous,
            now=NOW,
            max_release_age_hours=12,
            max_source_age_days=4,
        )

    def test_stale_e10_fails_even_when_global_gazole_sp95_are_fresh(self):
        report = self.evaluate(
            candidate({"Gazole": "2026-08-23", "SP95": "2026-08-23", "E10": "2026-08-18"}),
            baseline({"Gazole": "2026-08-22", "SP95": "2026-08-22", "E10": "2026-08-17"}),
        )
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("E10" in item and "stale" in item for item in report["failures"]))

    def test_regressed_e10_fails_even_when_other_fuels_advance(self):
        report = self.evaluate(
            candidate({"Gazole": "2026-08-23", "SP95": "2026-08-23", "E10": "2026-08-22"}),
            baseline({"Gazole": "2026-08-22", "SP95": "2026-08-22", "E10": "2026-08-23"}),
        )
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("E10" in item and "regressed" in item for item in report["failures"]))

    def test_fresh_e10_passes_with_other_required_fuels(self):
        report = self.evaluate(
            candidate({"Gazole": "2026-08-23", "SP95": "2026-08-23", "E10": "2026-08-23"}),
            baseline({"Gazole": "2026-08-22", "SP95": "2026-08-22", "E10": "2026-08-22"}),
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["failures"], [])


if __name__ == "__main__":
    unittest.main()
