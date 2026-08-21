from datetime import date, datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest

from carburantscorse2 import r2_guard_v2 as guard


class R2GuardT(unittest.TestCase):
    def observed_file(self):
        f = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        f.write('date,rotterdam_eur_l\n')
        for d, v in [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-20', 0.868), ('2026-05-21', 0.865), ('2026-05-22', 0.859),
        ]:
            f.write(f'{d},{v}\n')
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def meta_file(self):
        payload = {'rotterdam': {'corsica_calibration': {
            'territory': 'corsica', 'entry_date': '2026-04-08',
            'r1': 1.0486666666666666, 'k': 0.7329942783728567,
            'r2': 0.7686666666666667,
            'r1_source_dates': ['2026-04-03', '2026-04-06', '2026-04-07'],
            'exit_source_dates': ['2026-05-29', '2026-06-01', '2026-06-02'],
        }}}
        f = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, suffix='.json')
        json.dump(payload, f)
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def daily_file(self, rows):
        f = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        f.write('date,rotterdam_eur_l\n')
        for d, v in rows:
            f.write(f'{d.isoformat()},{v}\n')
        f.close()
        self.addCleanup(lambda: Path(f.name).unlink(missing_ok=True))
        return f.name

    def test_first_stale_day_is_declaration_plus_45(self):
        declared = datetime(2026, 6, 1, 8)
        first_stale = date(2026, 7, 16)
        self.assertTrue(guard.stale_price_admissible(
            declared, first_stale, 'corsica',
            observed_file=self.observed_file(), daily_file=self.daily_file([(first_stale, 0.769)]),
            shared_meta_file=self.meta_file(),
        ))

    def test_bdr_breach_and_recovery_stays_locked(self):
        declared = datetime(2026, 6, 1, 8)
        start = date(2026, 7, 16)
        rows = [(start, 0.870), (start + timedelta(days=1), 0.860), (start + timedelta(days=2), 0.900)]
        self.assertFalse(guard.stale_price_admissible(
            declared, start + timedelta(days=2), 'bdr',
            observed_file=self.observed_file(), daily_file=self.daily_file(rows),
            shared_meta_file=self.meta_file(),
        ))

    def test_new_target_declaration_resets_origin(self):
        new_declared = datetime(2026, 8, 10, 8)
        self.assertTrue(guard.stale_price_admissible(
            new_declared, date(2026, 8, 19), 'bdr',
            observed_file=self.observed_file(), daily_file=self.daily_file([]),
            shared_meta_file=self.meta_file(),
        ))

    def test_missing_or_future_declaration_fails_closed(self):
        observed = self.observed_file(); daily = self.daily_file([]); meta = self.meta_file()
        self.assertFalse(guard.stale_price_admissible(None, date(2026, 8, 19), 'corsica', observed_file=observed, daily_file=daily, shared_meta_file=meta))
        self.assertFalse(guard.stale_price_admissible(datetime(2026, 8, 20), date(2026, 8, 19), 'bdr', observed_file=observed, daily_file=daily, shared_meta_file=meta))


if __name__ == '__main__':
    unittest.main()
