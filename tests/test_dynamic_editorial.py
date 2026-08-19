from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'apply_dynamic_editorial.py'


def transformed_html():
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shutil.copy2(ROOT / 'index.html', work / 'index.html')
        subprocess.run([sys.executable, str(SCRIPT)], cwd=work, check=True, capture_output=True, text=True)
        return (work / 'index.html').read_text(encoding='utf-8')


HTML = transformed_html()


class DynamicEditorialTests(unittest.TestCase):
    def test_price_text_is_built_from_loaded_series(self):
        self.assertIn('function editorialMean(rows,field,start,end)', HTML)
        self.assertIn('function editorialYearMean(rows,year,field)', HTML)
        self.assertIn('function buildGazolePriceAnalysis()', HTML)
        self.assertIn('function buildSp95PriceAnalysis()', HTML)
        self.assertIn("editorialMean(all,'ecart',p.start,p.end)", HTML)
        self.assertIn("editorialMean(spAll,'ecart',p.start,p.end)", HTML)
        self.assertIn("editorialMean(e10All,'ecart',p.start,p.end)", HTML)

    def test_margin_text_is_dynamic_too(self):
        self.assertIn('function buildMarginAnalysis()', HTML)
        self.assertIn("editorialMean(all,'corse',start23,p.end)", HTML)
        self.assertIn("editorialMean(all,'bdr',start23,p.end)", HTML)
        self.assertIn("editorialYearMean(all,firstYear,'ecart')", HTML)

    def test_analysis_panel_uses_dynamic_builders(self):
        self.assertIn('panel.innerHTML=buildMarginAnalysis();', HTML)
        self.assertIn('panel.innerHTML=buildGazolePriceAnalysis();', HTML)
        self.assertIn('panel.innerHTML=buildSp95PriceAnalysis();', HTML)

    def test_period_end_and_year_labels_follow_data(self):
        self.assertIn('function getLatestDataYear()', HTML)
        self.assertIn("Toute la période (2022–'+getLatestDataYear()+')", HTML)
        self.assertIn('syncDynamicPeriodLabels();', HTML)
        self.assertIn('2022–${y}', HTML)

    def test_bouclier_current_status_comes_from_shared_metadata(self):
        self.assertIn('function editorialBouclierStatus(fuel)', HTML)
        self.assertIn('meta.current_active&&meta.current_active_since', HTML)
        self.assertIn("editorialBouclierStatus('Gazole')", HTML)
        self.assertIn("editorialBouclierStatus('SP95')", HTML)

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            shutil.copy2(ROOT / 'index.html', work / 'index.html')
            subprocess.run([sys.executable, str(SCRIPT)], cwd=work, check=True, capture_output=True, text=True)
            once = (work / 'index.html').read_text(encoding='utf-8')
            subprocess.run([sys.executable, str(SCRIPT)], cwd=work, check=True, capture_output=True, text=True)
            twice = (work / 'index.html').read_text(encoding='utf-8')
            self.assertEqual(once, twice)


if __name__ == '__main__':
    unittest.main()
