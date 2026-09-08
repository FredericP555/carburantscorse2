from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRESHNESS = ROOT / "freshness.js"


class FinalAuditUiClosureTests(unittest.TestCase):
    def setUp(self):
        self.text = FRESHNESS.read_text(encoding="utf-8")

    def test_ui04_compares_record_dates_before_using_post_sanction_wording(self):
        self.assertIn("overallPeak.date>sanctionPeak.date", self.text)
        self.assertIn("overallPeak.date<sanctionPeak.date", self.text)
        self.assertIn("Un niveau plus élevé avait déjà été observé auparavant", self.text)
        self.assertIn("Ce niveau a ensuite été dépassé", self.text)

    def test_ui05_validates_current_payload_and_neutralizes_embedded_fallback(self):
        self.assertIn("function validateDashboardPayload", self.text)
        self.assertIn("A4C_DATA_SOURCE_FAILED", self.text)
        self.assertIn("Aucun graphique ancien n’est affiché en secours silencieux", self.text)
        self.assertIn("loadDashboardData=guardedLoad", self.text)
        self.assertIn("bouclier ${fuel} absent", self.text)

    def test_ui06_low_height_landscape_has_scroll_and_readable_chart_floor(self):
        self.assertIn("@media (min-width:701px) and (max-height:520px)", self.text)
        self.assertIn("overflow-y:auto!important", self.text)
        self.assertIn("height:280px!important", self.text)
        self.assertIn("min-height:245px!important", self.text)

    def test_freshness_javascript_still_parses(self):
        completed = subprocess.run(
            ["node", "--check", str(FRESHNESS)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
