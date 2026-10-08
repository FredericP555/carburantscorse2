from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "monthly-territorial-dry-run.yml").read_text(encoding="utf-8")


class MonthlyCloudflareGateTests(unittest.TestCase):
    def test_github_schedule_is_removed_after_cloudflare_validation(self):
        self.assertNotIn("schedule:", WORKFLOW)
        self.assertNotIn("cron: '0 10 * * 2'", WORKFLOW)
        self.assertNotIn("cron: '0 11 * * 2'", WORKFLOW)
        self.assertNotIn("EVENT_SCHEDULE", WORKFLOW)
        self.assertNotIn("Non-selected UTC companion slot", WORKFLOW)

    def test_blank_workflow_dispatch_enforces_duplicate_gate(self):
        self.assertIn("REQUESTED_MONTH: ${{ github.event.inputs.month || '' }}", WORKFLOW)
        self.assertIn(
            "if [ \"$EVENT_NAME\" = 'workflow_dispatch' ] && [ -n \"$REQUESTED_MONTH\" ]; then",
            WORKFLOW,
        )
        self.assertIn(
            "Automatic workflow_dispatch without explicit month: duplicate gate enforced.",
            WORKFLOW,
        )
        self.assertNotIn(
            "if [ \"$EVENT_NAME\" = 'workflow_dispatch' ]; then\n"
            "            echo 'Manual dry-run: duplicate gate intentionally bypassed.'",
            WORKFLOW,
        )
        dispatch_marker = WORKFLOW.index(
            "Automatic workflow_dispatch without explicit month: duplicate gate enforced."
        )
        artifact_lookup = WORKFLOW.index('artifact_name="monthly-territorial-dry-run-$MONTH"')
        self.assertLess(dispatch_marker, artifact_lookup)

    def test_explicit_month_keeps_manual_backfill_semantics(self):
        manual = WORKFLOW.index("Explicit manual backfill: duplicate gate intentionally bypassed.")
        artifact_lookup = WORKFLOW.index('artifact_name="monthly-territorial-dry-run-$MONTH"')
        self.assertLess(manual, artifact_lookup)
        self.assertIn("extra+=(--allow-backfill)", WORKFLOW)
        self.assertIn(
            "github.event_name }}\" = 'workflow_dispatch' ] && [ -n \"${{ github.event.inputs.month || '' }}\" ]",
            WORKFLOW,
        )

    def test_only_supported_triggers_are_accepted(self):
        self.assertIn("if [ \"$EVENT_NAME\" = 'workflow_dispatch' ]; then", WORKFLOW)
        self.assertIn('echo "Unsupported monthly trigger: $EVENT_NAME" >&2', WORKFLOW)
        self.assertIn("exit 2", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
