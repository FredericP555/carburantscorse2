from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRESHNESS = ROOT / "freshness.js"
INDEX = ROOT / "index.html"


class UiAuditFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freshness = FRESHNESS.read_text(encoding="utf-8")
        cls.index = INDEX.read_text(encoding="utf-8")

    def test_ui02_date_only_chart_timestamp_uses_local_noon(self):
        self.assertIn("function dateOnlyLocalTs", self.freshness)
        self.assertIn("new Date(y,m-1,d,12,0,0,0).getTime()", self.freshness)
        self.assertIn("ts=patchedTs", self.freshness)

    def test_ui03_stats_are_recomputed_from_visible_period(self):
        self.assertIn("function visibleRowsForCurrentPeriod", self.freshness)
        self.assertIn("setStats=patchedSetStats", self.freshness)
        self.assertIn("const rows=visibleRowsForCurrentPeriod(raw)", self.freshness)

    def test_ui04_sp95_record_is_derived_from_weekly_data(self):
        self.assertIn("const patchedSp95PriceAnalysis=function()", self.freshness)
        self.assertIn("const sanctionPeak=maxRow(weekly,'ecart','2025-11-17','2025-12-31')", self.freshness)
        self.assertIn("const overallPeak=maxRow(weekly,'ecart')", self.freshness)
        self.assertIn("buildSp95PriceAnalysis=patchedSp95PriceAnalysis", self.freshness)

    def test_runtime_patch_loads_after_inline_code_and_before_body_close(self):
        freshness_pos = self.index.rfind('<script src="freshness.js"></script>')
        self.assertGreaterEqual(freshness_pos, 0)
        previous_inline_close = self.index.rfind('</script>', 0, freshness_pos)
        self.assertGreater(freshness_pos, previous_inline_close)
        self.assertLess(freshness_pos, self.index.rfind('</body>'))
        self.assertIn("installC2AuditUiFixes();", self.freshness)

    def test_freshness_javascript_syntax(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available")
        proc = subprocess.run([node, "--check", str(FRESHNESS)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
