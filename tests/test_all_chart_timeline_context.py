from pathlib import Path
import unittest

HTML = Path('index.html').read_text(encoding='utf-8')

class TimelineAllChartsTests(unittest.TestCase):
    def test_full_total_policy_information_matches_c1(self):
        self.assertIn('1,99 €/L TTC</b> d’août 2023 au 19 mars 2026', HTML)
        self.assertIn('2,09 €/L TTC</b> du 20 mars au 7 avr. 2026', HTML)
        self.assertIn('2,25 €/L TTC</b> depuis le 8 avr. 2026', HTML)
        self.assertIn('1,99 €/L TTC</b> depuis mars 2023', HTML)

    def test_active_windows_are_consumed_from_c1_metadata(self):
        self.assertIn('function getBouclierMeta(ck)', HTML)
        self.assertIn('function getBouclierRanges(ck)', HTML)
        self.assertIn('meta&&Array.isArray(meta.ranges)?meta.ranges:[]', HTML)
        self.assertIn("getBouclierRanges(ck).forEach", HTML)

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
