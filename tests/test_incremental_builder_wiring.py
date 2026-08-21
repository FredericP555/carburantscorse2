import unittest
from unittest import mock

from scripts import build_append_candidate_incremental as inc


class IncrementalBuilderWiringT(unittest.TestCase):
    def test_release_tag_is_forwarded_to_original_loader(self):
        seen = {}

        def fake_loader(years, mode, *, release_tag=None):
            seen['years'] = years
            seen['mode'] = mode
            seen['release_tag'] = release_tag
            return [], {'release_tag': release_tag}

        with mock.patch.object(inc, '_original_load_official', fake_loader), \
             mock.patch.object(inc, '_original_load_categories', lambda _path: {}), \
             mock.patch.object(inc, 'resolve_from_observations', lambda *a, **k: {}):
            rows, source = inc._load_official_and_resolve(
                (2025, 2026), 'shared', release_tag='a4c-shared-test'
            )

        self.assertEqual(rows, [])
        self.assertEqual(source['release_tag'], 'a4c-shared-test')
        self.assertEqual(seen['release_tag'], 'a4c-shared-test')

    def test_nonfinite_rotterdam_is_rejected(self):
        import pandas as pd

        daily = pd.DataFrame({'rotterdam_eur_l': [0.8, float('inf')]})
        observed = pd.DataFrame({'rotterdam_eur_l': [0.8]})
        with mock.patch.object(inc, '_original_load_rotterdam', lambda *a: (daily, observed)):
            with self.assertRaises(RuntimeError):
                inc._load_shared_rotterdam_finite('2026-01-01', '2026-01-02')


if __name__ == '__main__':
    unittest.main()
