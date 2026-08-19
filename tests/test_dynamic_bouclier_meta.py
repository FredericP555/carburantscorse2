from pathlib import Path
import unittest


class DynamicBouclierMetaTests(unittest.TestCase):
    def test_shared_manifest_metadata_is_carried_into_candidate(self):
        reader = Path('a4c_common/shared_release.py').read_text(encoding='utf-8')
        builder = Path('scripts/build_append_candidate.py').read_text(encoding='utf-8')
        self.assertIn('"bouclier": metadata.get("bouclier")', reader)
        self.assertIn('"bouclier": official_source.get("bouclier") or baseline_meta.get("bouclier")', builder)

    def test_dashboard_prefers_dynamic_ranges_with_static_fallback(self):
        html = Path('index.html').read_text(encoding='utf-8')
        self.assertIn('function getBouclierRanges(ck)', html)
        self.assertIn("Array.isArray(meta.ranges)?meta.ranges:(BOUCLIER[ck]||[])", html)
        self.assertIn("getBouclierRanges(ck).forEach", html)
        self.assertIn('current_active_since', html)


if __name__ == '__main__':
    unittest.main()
