from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from scripts.check_shared_freshness import evaluate_shared_freshness


ROOT = Path(__file__).resolve().parents[1]
RETRY_WORKFLOW = ROOT / ".github" / "workflows" / "retry-after-c1.yml"
WATCHDOG_WORKFLOW = ROOT / ".github" / "workflows" / "watchdog-weekly.yml"

NOW = datetime(2026, 9, 8, 6, 30, tzinfo=timezone.utc)


def candidate(*, tag: str, release_at: str, source_max: str) -> dict:
    return {
        "official_ingestion_source": "c1-github-release",
        "official_shared_release_tag": tag,
        "official_shared_release_published_at": release_at,
        "official_shared_source_max_date": source_max,
        "official_shared_source_max_date_by_fuel": {
            "Gazole": source_max,
            "SP95": source_max,
            "E10": source_max,
        },
    }


def baseline(source_max: str = "2026-09-06") -> dict:
    return {
        "official_shared_source_max_date": source_max,
        "official_shared_source_max_date_by_fuel": {
            "Gazole": source_max,
            "SP95": source_max,
            "E10": source_max,
        },
    }


class DelayedC1RecoveryEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retry = RETRY_WORKFLOW.read_text(encoding="utf-8")
        cls.watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")

    def freshness(self, current: dict, previous: dict) -> dict:
        return evaluate_shared_freshness(
            current,
            previous,
            now=NOW,
            max_release_age_hours=12,
            max_source_age_days=4,
        )

    def test_step_1_c2_refuses_old_c1_when_c1_is_late(self):
        old_c1 = candidate(
            tag="a4c-v2-shared-20260907T170000Z-old",
            release_at="2026-09-07T17:00:00Z",
            source_max="2026-09-07",
        )
        report = self.freshness(old_c1, baseline())

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("Release is stale" in failure for failure in report["failures"]))

    def test_step_2_new_c1_release_passes_the_same_production_gate(self):
        new_c1 = candidate(
            tag="a4c-v2-shared-20260908T061500Z-new",
            release_at="2026-09-08T06:15:00Z",
            source_max="2026-09-07",
        )
        report = self.freshness(new_c1, baseline())

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["source_progression"], "advanced")
        self.assertEqual(report["failures"], [])

    def test_step_3_retry_detects_new_unconsumed_c1_and_dispatches_full_update(self):
        mismatch_clause = 'elif [ "$data_tag" != "$tag" ] || [ "$summary_tag" != "$tag" ]; then'
        self.assertIn(mismatch_clause, self.retry)
        mismatch_pos = self.retry.index(mismatch_clause)
        full_update_pos = self.retry.index('action="full-update"', mismatch_pos)
        repair_pos = self.retry.index('action="repair-publication"', mismatch_pos)
        self.assertLess(full_update_pos, repair_pos)

        dispatch_guard = "steps.state.outputs.action == 'full-update'"
        dispatch_command = "gh workflow run update-weekly.yml"
        self.assertIn(dispatch_guard, self.retry)
        self.assertIn(dispatch_command, self.retry)
        self.assertIn("steps.clock.outputs.dry_run != 'true'", self.retry)

    def test_step_4_watchdog_also_recovers_before_late_followups(self):
        mismatch_clause = 'elif [ "$data_tag" != "$latest_today" ] || [ "$summary_tag" != "$latest_today" ]; then'
        self.assertIn(mismatch_clause, self.watchdog)
        self.assertIn('action="full-update"', self.watchdog[self.watchdog.index(mismatch_clause):])
        self.assertIn("gh workflow run update-weekly.yml", self.watchdog)
        self.assertIn("local_hour in {9, 10}", self.watchdog)

    def test_step_5_retry_has_repeated_monday_slots_and_tuesday_safety_net(self):
        self.assertIn("local_hour in {11, 14, 17, 20}", self.retry)
        self.assertIn("local_dow == 2 and local_hour == 7", self.retry)
        for cron in (
            "47 9 * * 1",
            "47 12 * * 1",
            "47 15 * * 1",
            "47 18 * * 1",
            "47 5 * * 2",
        ):
            self.assertIn(cron, self.retry)


if __name__ == "__main__":
    unittest.main()
