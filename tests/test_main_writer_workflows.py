from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class MainWriterWorkflowContracts(unittest.TestCase):
    def test_active_c2_main_writers_share_one_concurrency_group(self):
        for name in ("update-weekly.yml", "publish-homepage-summary.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("group: c2-main-writers", text, name)
            self.assertIn("cancel-in-progress: false", text, name)

    def test_active_c2_main_writers_guard_remote_main_before_push(self):
        for name in ("update-weekly.yml", "publish-homepage-summary.yml"):
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("WRITER_BASE_SHA", text, name)
            self.assertIn("git fetch origin", text, name)
            self.assertIn("origin/${GITHUB_REF_NAME:-main}", text, name)
            self.assertIn("Main advanced while this writer was running", text, name)

    def test_freshness_badge_workflow_is_read_only(self):
        text = (WORKFLOWS / "freshness-badge.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("pages/builds", text)

    def test_completed_one_off_ufip_repair_workflow_is_archived(self):
        self.assertFalse((WORKFLOWS / "repair-ufip-margin-20260817.yml").exists())


if __name__ == "__main__":
    unittest.main()
