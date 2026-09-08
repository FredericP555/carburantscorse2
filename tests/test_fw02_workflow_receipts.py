from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "watchdog-weekly.yml",
    ROOT / ".github" / "workflows" / "retry-after-c1.yml",
)


class FW02WorkflowReceiptTests(unittest.TestCase):
    def test_watchdog_and_retry_validate_receipts_against_current_content(self):
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", text)
                self.assertIn("python scripts/validate_current_c2_receipt.py", text)
                self.assertIn("--pages-data-file /tmp/c2-pages-data.json", text)
                self.assertIn("--pages-summary-file /tmp/c2-pages-summary.json", text)
                self.assertNotIn("jq -e --arg tag", text)

    def test_business_success_none_branch_requires_validated_business_run(self):
        for path in WORKFLOWS:
            with self.subTest(workflow=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn('elif [ -n "$business_run" ]', text) if path.name == "watchdog-weekly.yml" else self.assertIn('if [ -n "$business_run" ]', text)
                validator_pos = text.index("python scripts/validate_current_c2_receipt.py")
                assignment_pos = text.index('business_run="$run_id"', validator_pos)
                self.assertLess(validator_pos, assignment_pos)


if __name__ == "__main__":
    unittest.main()
