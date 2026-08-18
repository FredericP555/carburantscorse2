from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionBoundaryTests(unittest.TestCase):
    def test_production_entrypoint_uses_publication_profile_not_research_profile(self):
        source = (ROOT / "scripts" / "build_append_candidate.py").read_text(encoding="utf-8")
        self.assertIn("from carburantscorse2.publication import", source)
        self.assertNotIn("from carburantscorse2.method import", source)

    def test_research_method_is_explicitly_marked_non_production(self):
        source = (ROOT / "carburantscorse2" / "method.py").read_text(encoding="utf-8")
        self.assertIn("RESEARCH-ONLY", source)
        self.assertIn("production updater must use", source)


if __name__ == "__main__":
    unittest.main()
