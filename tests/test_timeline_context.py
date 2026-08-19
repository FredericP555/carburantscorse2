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

    def test_gazole_shield_and_promos_match_c1(self):
        periods = (
            ('2023-08-31','2023-10-13'), ('2023-10-24','2023-10-30'),
            ('2026-03-20','2026-04-06'), ('2026-04-08','2026-05-27'),
            ('2026-04-30','2026-05-03'), ('2026-05-08','2026-05-10'),
            ('2026-05-14','2026-05-17'), ('2026-05-23','2026-05-25'),
        )
        for d1, d2 in periods:
            self.assertIn(f"{{d1:'{d1}',d2:'{d2}'}}", self.html)

    def test_sp95_shield_periods_match_c1(self):
        periods = (
            ('2023-02-20','2023-03-19'), ('2023-03-27','2023-05-02'),
            ('2023-06-09','2023-06-21'), ('2023-07-25','2023-10-07'),
            ('2024-02-20','2024-03-01'), ('2024-03-07','2024-06-05'),
            ('2024-07-01','2024-07-16'), ('2026-03-13','2026-05-28'),
        )
        for d1, d2 in periods:
            self.assertIn(f"{{d1:'{d1}',d2:'{d2}'}}", self.html)

    def test_legacy_context_is_gone(self):
        for legacy in ('const PERIODES=', 'Sanction concurrence', "id=\"li-209\"", "id=\"li-225\""):
            self.assertNotIn(legacy, self.html)


if __name__ == '__main__':
    unittest.main()
