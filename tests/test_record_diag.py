from pathlib import Path
import json
import statistics
import unittest


class RecordDiag(unittest.TestCase):
    def test_print_gazole_records(self):
        d = json.loads(Path('data.json').read_text(encoding='utf-8'))
        out = {}
        for gran in ('daily', 'weekly'):
            for scope in ('all', 'reseau'):
                rows = d['DATA']['gazole']['sp95'][gran][scope]
                full = max(rows, key=lambda r: r['ecart'])
                through_2025 = [r for r in rows if r['date'] <= '2025-12-31']
                max_through_2025 = max(through_2025, key=lambda r: r['ecart'])
                dec = [r for r in rows if r['date'].startswith('2025-12')]
                decmax = max(dec, key=lambda r: r['ecart'])
                decmean = round(statistics.fmean(r['ecart'] for r in dec), 3)
                post = [r for r in rows if r['date'] >= '2025-11-17']
                postmax = max(post, key=lambda r: r['ecart'])
                top_dec = sorted(dec, key=lambda r: r['ecart'], reverse=True)[:10]
                out[f'{gran}/{scope}'] = {
                    'full_max': full,
                    'max_through_2025': max_through_2025,
                    'dec2025_max': decmax,
                    'dec2025_mean': decmean,
                    'post_sanction_max': postmax,
                    'top_dec': top_dec,
                }
        print('A4C_GAZOLE_RECORD_DIAG=' + json.dumps(out, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
