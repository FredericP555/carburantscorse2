from datetime import date
import unittest

from carburantscorse2 import shield_phase_v2 as s


class ShieldPhaseT(unittest.TestCase):
    def test_reads_c1_phase_for_day(self):
        meta = {
            'Gazole': {
                'phases': [
                    {'d1': '2026-03-20', 'd2': '2026-04-07', 'cap': 2.09, 'phase_id': 'g1'},
                    {'d1': '2026-04-08', 'd2': '2026-05-01', 'cap': 2.25, 'phase_id': 'g2'},
                ]
            }
        }
        phase = s.phase_for_day(meta, 'Gazole', date(2026, 4, 9))
        self.assertIsNotNone(phase)
        self.assertEqual(phase.started_on, date(2026, 4, 8))
        self.assertEqual(phase.cap, 2.25)
        self.assertEqual(phase.phase_id, 'g2')

    def test_outside_effective_phase_returns_none(self):
        meta = {'SP95': {'phases': [{'d1': '2026-03-01', 'd2': '2026-03-31', 'cap': 1.99}]}}
        self.assertIsNone(s.phase_for_day(meta, 'SP95', date(2026, 4, 1)))

    def test_invalid_phase_fails_closed(self):
        meta = {'Gazole': {'phases': [{'d1': 'bad', 'd2': '2026-04-07', 'cap': 2.09}]}}
        with self.assertRaises(ValueError):
            s.phase_for_day(meta, 'Gazole', date(2026, 4, 1))


if __name__ == '__main__':
    unittest.main()
