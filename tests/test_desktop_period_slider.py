import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DesktopPeriodSliderTests(unittest.TestCase):
    def test_existing_selector_is_enabled_on_desktop(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "freshness.js").read_text(encoding="utf-8")

        self.assertIn('id="periode-slider"', html)
        self.assertIn('id="slider-mois"', html)
        self.assertIn('window.usePeriodSlider=function(){return true;};', js)
        self.assertIn("panel.style.display=window.innerWidth<=700?'block':'flex';", js)

    def test_same_existing_12_month_default_is_kept(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("let currentMonths=12;", html)
        self.assertIn('value="12"', html)
        self.assertIn("lbl.textContent='12 derniers mois';", html)

    def test_desktop_slider_has_compact_layout(self):
        js = (ROOT / "freshness.js").read_text(encoding="utf-8")
        self.assertIn('@media(min-width:701px)', js)
        self.assertIn('#periode-slider{align-items:center;gap:12px', js)
        self.assertIn('#periode-slider input[type=range]{width:min(360px,40vw)', js)


if __name__ == "__main__":
    unittest.main()
