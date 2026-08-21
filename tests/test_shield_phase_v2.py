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
        meta = {'SP95': {'phases': [
            {'d1': '2026-03-01', 'd2': '2026-03-31', 'cap': 1.99, 'phase_id': 's1'}
        ]}}
        self.assertIsNone(s.phase_for_day(meta, 'SP95', date(2026, 4, 1)))

    def test_missing_phases_is_explicit_error(self):
        with self.assertRaises(RuntimeError):
            s.phase_for_day({'Gazole': {}}, 'Gazole', date(2026, 4, 1))

    def test_invalid_phase_fails_closed(self):
        meta = {'Gazole': {'phases': [
            {'d1': 'bad', 'd2': '2026-04-07', 'cap': 2.09, 'phase_id': 'g1'}
        ]}}
        with self.assertRaises(RuntimeError):
            s.phase_for_day(meta, 'Gazole', date(2026, 4, 1))

    def test_nonfinite_cap_fails_closed(self):
        meta = {'Gazole': {'phases': [
            {'d1': '2026-03-20', 'd2': '2026-04-07', 'cap': float('nan'), 'phase_id': 'g1'}
        ]}}
        with self.assertRaises(RuntimeError):
            s.validated_phases(meta, 'Gazole')

    def test_overlap_and_duplicate_id_fail_closed(self):
        overlap = {'Gazole': {'phases': [
            {'d1': '2026-03-20', 'd2': '2026-04-08', 'cap': 2.09, 'phase_id': 'g1'},
            {'d1': '2026-04-08', 'd2': '2026-05-01', 'cap': 2.25, 'phase_id': 'g2'},
        ]}}
        with self.assertRaises(RuntimeError):
            s.validated_phases(overlap, 'Gazole')

        duplicate = {'Gazole': {'phases': [
            {'d1': '2026-03-20', 'd2': '2026-04-07', 'cap': 2.09, 'phase_id': 'g1'},
            {'d1': '2026-04-08', 'd2': '2026-05-01', 'cap': 2.25, 'phase_id': 'g1'},
        ]}}
        with self.assertRaises(RuntimeError):
            s.validated_phases(duplicate, 'Gazole')

    def test_double_cap_period_starts_when_second_fuel_becomes_effective(self):
        meta = {
            'Gazole': {'phases': [
                {'d1': '2026-10-10', 'd2': '2026-11-30', 'cap': 2.25, 'phase_id': 'g-new'}
            ]},
            'SP95': {'phases': [
                {'d1': '2026-09-20', 'd2': '2026-12-15', 'cap': 1.99, 'phase_id': 's-old'}
            ]},
        }
        period = s.double_cap_period_for_day(meta, date(2026, 10, 20))
        self.assertIsNotNone(period)
        self.assertEqual(period.started_on, date(2026, 10, 10))
        self.assertEqual(period.ended_on, date(2026, 11, 30))


if __name__ == '__main__':
    unittest.main()
