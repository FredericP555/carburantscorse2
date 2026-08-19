from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "freshness.js").read_text(encoding="utf-8")

class AdaptiveTimeAxisTests(unittest.TestCase):
    def test_short_windows_get_bimonthly_markers(self):
        self.assertIn("spanMonths<=15?2:spanMonths<=30?3:12", JS)

    def test_existing_axis_builder_is_overridden(self):
        self.assertIn("buildAnnualTicks=function(minTs,maxTs)", JS)
        self.assertIn("formatAnnualTick=function(v)", JS)

if __name__ == "__main__":
    unittest.main()
