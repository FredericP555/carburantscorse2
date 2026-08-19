from pathlib import Path
import unittest

HTML = Path('index.html').read_text(encoding='utf-8')

class TimelineAllChartsTests(unittest.TestCase):
    def test_full_total_policy_information_matches_c1(self):
        self.assertIn('1,99 €/L TTC</b> d’août 2023 au 19 mars 2026', HTML)
        self.assertIn('2,09 €/L TTC</b> du 20 mars au 7 avr. 2026', HTML)
        self.assertIn('2,25 €/L TTC</b> depuis le 8 avr. 2026', HTML)
        self.assertIn('1,99 €/L TTC</b> depuis mars 2023', HTML)

    def test_active_windows_are_exact_c1_windows(self):
        expected = [
            "{d1:'2023-08-31',d2:'2023-10-13'}",
            "{d1:'2023-10-24',d2:'2023-10-30'}",
            "{d1:'2026-03-20',d2:'2026-04-06'}",
            "{d1:'2026-04-08',d2:'2026-05-27'}",
            "{d1:'2023-02-20',d2:'2023-03-19'}",
            "{d1:'2023-03-27',d2:'2023-05-02'}",
            "{d1:'2023-06-09',d2:'2023-06-21'}",
            "{d1:'2023-07-25',d2:'2023-10-07'}",
            "{d1:'2024-02-20',d2:'2024-03-01'}",
            "{d1:'2024-03-07',d2:'2024-06-05'}",
            "{d1:'2024-07-01',d2:'2024-07-16'}",
            "{d1:'2026-03-13',d2:'2026-05-28'}",
        ]
        for marker in expected:
            self.assertIn(marker, HTML)

    def test_events_match_c1_and_use_top_down_labels(self):
        for marker in [
            "date:'2022-02-24',label:'Invasion Ukraine'",
            "date:'2025-11-17',label:'Sanctions Autorité'",
            "date:'2026-02-28',label:\"Guerre d'Iran\"",
        ]:
            self.assertIn(marker, HTML)
        self.assertIn("ctx.translate(xp+3,top+20);ctx.rotate(Math.PI/2)", HTML)
        self.assertIn("const isMobile=window.innerWidth<700", HTML)
        self.assertIn('id="legende-events-mobile"', HTML)

    def test_timeline_plugin_is_shared_by_all_chart_builds(self):
        self.assertIn('plugins:[makePlugin(minTs,maxTs,ck),crosshairPlugin]', HTML)
        self.assertIn("buildOne('chart1'", HTML)
        self.assertIn("buildOne('chart2'", HTML)
        self.assertIn("d={all:MARGES_GZ.all,reseau:MARGES_GZ.reseau}", HTML)

    def test_x_axis_uses_annual_markers_like_c1(self):
        self.assertIn('function buildAnnualTicks(minTs,maxTs)', HTML)
        self.assertIn("return 'jan '+String(d.getFullYear()).slice(2)", HTML)
        self.assertIn('afterBuildTicks:function(scale)', HTML)

if __name__ == '__main__':
    unittest.main()
