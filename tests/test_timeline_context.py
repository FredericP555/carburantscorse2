from pathlib import Path
import unittest


INDEX = Path(__file__).resolve().parents[1] / "index.html"


class TimelineContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")

    def test_event_markers_match_c1(self):
        for marker in (
            "date:'2022-02-24',label:'Invasion Ukraine'",
            "date:'2025-11-17',label:'Sanctions Autorité'",
            'date:\'2026-02-28\',label:"Guerre d\'Iran"',
        ):
            self.assertIn(marker, self.html)

    def test_total_2022_discount_periods_match_c1(self):
        self.assertIn("{d1:'2022-09-01',d2:'2022-11-15',alpha_fill:0.18}", self.html)
        self.assertIn("{d1:'2022-11-16',d2:'2022-12-31',alpha_fill:0.12}", self.html)

    def test_shield_ranges_come_only_from_c1_metadata(self):
        self.assertIn('function getBouclierRanges(ck)', self.html)
        self.assertIn('meta&&Array.isArray(meta.ranges)?meta.ranges:[]', self.html)
        self.assertIn("getBouclierRanges(ck).forEach", self.html)
        self.assertNotIn('meta.ranges)?meta.ranges:(BOUCLIER[ck]||[])', self.html)

    def test_gazole_promos_remain_separate_context(self):
        periods = (
            ('2026-04-30','2026-05-03'), ('2026-05-08','2026-05-10'),
            ('2026-05-14','2026-05-17'), ('2026-05-23','2026-05-25'),
        )
        for d1, d2 in periods:
            self.assertIn(f"{{d1:'{d1}',d2:'{d2}'}}", self.html)

    def test_legacy_context_is_gone(self):
        for legacy in ('const PERIODES=', 'Sanction concurrence', "id=\"li-209\"", "id=\"li-225\""):
            self.assertNotIn(legacy, self.html)


if __name__ == '__main__':
    unittest.main()
