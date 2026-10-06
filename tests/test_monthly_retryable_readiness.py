from pathlib import Path
import unittest

from scripts.check_monthly_readiness import classify_readiness


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "monthly-territorial-dry-run.yml").read_text(encoding="utf-8")


class MonthlyRetryableReadinessTests(unittest.TestCase):
    def test_no_failed_checks_is_ready(self):
        self.assertEqual(classify_readiness([{"key": "ok", "ok": True}]), ("ready", []))

    def test_expected_data_lags_are_retryable(self):
        keys = [
            "c2_complete_through_month_end",
            "c2_success_state_is_post_month_end",
            "ufip_covers_month_end",
        ]
        checks = [{"key": key, "ok": False} for key in keys]
        self.assertEqual(classify_readiness(checks), ("retryable_not_ready", keys))

    def test_structural_failure_remains_fatal(self):
        checks = [
            {"key": "ufip_covers_month_end", "ok": False},
            {"key": "geography_has_19_epci", "ok": False},
        ]
        kind, failed = classify_readiness(checks)
        self.assertEqual(kind, "fatal_not_ready")
        self.assertEqual(failed, ["ufip_covers_month_end", "geography_has_19_epci"])

    def test_missing_business_success_is_a_clean_wait(self):
        self.assertIn("id: business", WORKFLOW)
        self.assertIn("business_ready=false", WORKFLOW)
        self.assertIn("wait_reason=business_success_missing", WORKFLOW)
        self.assertIn(
            "No still-current C2 business-success receipt yet; monthly generation will wait for a retry.",
            WORKFLOW,
        )
        self.assertNotIn('test -n "$found"', WORKFLOW)

    def test_retryable_readiness_does_not_fail_the_job(self):
        self.assertIn("id: readiness", WORKFLOW)
        self.assertIn("retryable_not_ready)", WORKFLOW)
        self.assertIn("monthly_ready=false", WORKFLOW)
        self.assertNotIn("--fail-if-not-ready", WORKFLOW)
        self.assertIn("Fatal monthly readiness failure", WORKFLOW)
        self.assertIn("exit 2", WORKFLOW)

    def test_not_ready_run_cannot_create_canonical_monthly_artifact(self):
        self.assertIn(
            "if: always() && steps.readiness.outputs.monthly_ready == 'true'",
            WORKFLOW,
        )
        self.assertIn(
            "name: monthly-territorial-dry-run-${{ needs.prepare.outputs.month }}",
            WORKFLOW,
        )
        self.assertIn(
            "No canonical monthly artifact was created; a later retry may continue.",
            WORKFLOW,
        )

    def test_monthly_engine_only_runs_after_ready(self):
        guarded_steps = [
            "Run two-month source guards with bounded BDR backfill",
            "Build monthly dataset with the integrated main engine",
            "Exercise the widget generically in temporary storage",
            "Create and re-check an ephemeral final receipt",
            "Write dry-run manifest",
        ]
        for name in guarded_steps:
            marker = (
                f"- name: {name}\n"
                "        if: steps.readiness.outputs.monthly_ready == 'true'"
            )
            self.assertIn(marker, WORKFLOW)


if __name__ == "__main__":
    unittest.main()
