from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "update-weekly.yml").read_text(encoding="utf-8")


class WeeklyScheduleGateTests(unittest.TestCase):
    def test_external_dispatch_replaces_internal_dst_crons(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"(?m)^\s*schedule:\s*$")
        self.assertNotRegex(WORKFLOW, r"(?m)^\s*-\s*cron:")

        label = re.search(r"name: Select the 08:(\d{2}) Europe/Paris slot", WORKFLOW)
        self.assertIsNotNone(label)
        self.assertEqual(int(label.group(1)), 7, "C2 external dispatch contract must remain at 08:07 Europe/Paris")

        self.assertRegex(
            WORKFLOW,
            r"if event == 'workflow_dispatch':\s+run = True\s+else:",
            "An external workflow_dispatch must be accepted directly without a GitHub cron.",
        )

    def test_bot_triggered_updates_explicitly_dispatch_business_verification(self):
        self.assertIn("actions: write", WORKFLOW)
        self.assertIn("github.actor == 'github-actions[bot]'", WORKFLOW)
        self.assertIn("github.ref_name == github.event.repository.default_branch", WORKFLOW)
        self.assertIn("gh workflow run verify-c2-publication.yml", WORKFLOW)

        commit_step = WORKFLOW.index("name: Commit production data, registry and homepage summary together")
        verify_step = WORKFLOW.index("name: Dispatch C2 business verification for bot-triggered updates")
        self.assertLess(commit_step, verify_step)

    def test_gate_selects_only_the_matching_utc_hour(self):
        self.assertIn("scheduled_hour = int(parts[1])", WORKFLOW)
        self.assertIn("run = scheduled_hour == expected_utc_hour", WORKFLOW)
        self.assertNotIn("scheduled_minute", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
