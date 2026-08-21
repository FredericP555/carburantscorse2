from datetime import date, datetime, timedelta
from pathlib import Path
import json
import math
import tempfile
import unittest

from carburantscorse2 import reliability_policy_v2 as p
from carburantscorse2 import rotterdam_calibration_v2 as rc

D = date(2026, 8, 19)


class T(unittest.TestCase):
    def ev(self, **k):
        args = dict(
            day=D,
            region_kind='corsica',
            target_fuel='SP95',
            last_declared_at=datetime(2026, 3, 1),
            last_price=1.99,
        )
        args.update(k)
        return p.evaluate(**args)

    def shield_args(self, **extra):
        args = dict(
            is_total=True,
            shield_effective=True,
            applicable_cap=1.99,
            phase_started_on=date(2026, 3, 20),
        )
        args.update(extra)
        return args

    def test_45(self):
        self.assertTrue(self.ev(last_declared_at=datetime(2026, 7, 6)).eligible)
        self.assertFalse(self.ev(last_declared_at=datetime(2026, 7, 5)).eligible)

    def test_cap_tolerance_exact_millieuro_boundaries(self):
        self.assertTrue(p.at_cap(1.988, 1.99))
        self.assertTrue(p.at_cap(1.991, 1.99))
        self.assertFalse(p.at_cap(1.987, 1.99))
        self.assertFalse(p.at_cap(1.992, 1.99))
        self.assertTrue(p.at_cap(2.091, 2.09))
        self.assertTrue(p.at_cap(2.251, 2.25))

    def test_corse_single_cap_cross_liveness_renews_45_days(self):
        d = self.ev(**self.shield_args(activity_by_fuel={'Gazole': datetime(2026, 8, 10)}))
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'bouclier_vivacite_45j_renouvelee')

    def test_corse_single_cap_e10_does_not_prove_liveness(self):
        d = self.ev(**self.shield_args(activity_by_fuel={'E10': datetime(2026, 8, 18)}))
        self.assertFalse(d.eligible)

    def test_bdr_single_cap_any_other_fuel_renews_45_days(self):
        d = self.ev(
            region_kind='mainland',
            **self.shield_args(activity_by_fuel={'E10': datetime(2026, 8, 18)}),
        )
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'bouclier_vivacite_45j_renouvelee')

    def test_bdr_single_cap_has_no_arbitrary_90_day_stop(self):
        d = self.ev(
            region_kind='mainland',
            last_declared_at=datetime(2026, 3, 10),
            **self.shield_args(activity_by_fuel={'E10': datetime(2026, 8, 18)}),
        )
        self.assertTrue(d.eligible)

    def test_stale_e10_cannot_use_shield_exception(self):
        d = self.ev(
            target_fuel='E10',
            last_price=1.80,
            **self.shield_args(applicable_cap=1.80, activity_by_fuel={'Gazole': datetime(2026, 8, 18)}),
        )
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'exception_carburant_non_principal')

    def test_corse_double_cap_requires_r2_even_with_cross_liveness(self):
        d = self.ev(**self.shield_args(
            activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
            gazole_price=2.25, gazole_cap=2.25,
            sp95_price=1.99, sp95_cap=1.99,
            rotterdam_stale_price_admissible=False,
        ))
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_verrouille')

    def test_corse_double_cap_r2_admissible(self):
        d = self.ev(**self.shield_args(
            gazole_price=2.25, gazole_cap=2.25,
            sp95_price=1.99, sp95_cap=1.99,
            rotterdam_stale_price_admissible=True,
        ))
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_admissible')

    def test_bdr_double_cap_requires_nonprincipal_liveness(self):
        d = self.ev(
            region_kind='mainland',
            **self.shield_args(
                activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
                gazole_price=2.25, gazole_cap=2.25,
                sp95_price=1.99, sp95_cap=1.99,
                rotterdam_stale_price_admissible=True,
            ),
        )
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_bdr_sans_vivacite_autre_carburant')

    def test_bdr_double_cap_requires_liveness_and_r2(self):
        common = dict(
            region_kind='mainland',
            **self.shield_args(
                activity_by_fuel={'E10': datetime(2026, 8, 18)},
                gazole_price=2.25, gazole_cap=2.25,
                sp95_price=1.99, sp95_cap=1.99,
            ),
        )
        low = self.ev(**common, rotterdam_stale_price_admissible=False)
        self.assertFalse(low.eligible)
        self.assertEqual(low.reason, 'double_plafond_rotterdam_verrouille')
        high = self.ev(**common, rotterdam_stale_price_admissible=True)
        self.assertTrue(high.eligible)
        self.assertEqual(high.reason, 'double_plafond_bdr_vivacite_et_rotterdam')

    def test_no_resurrection_when_stale_at_phase_entry(self):
        d = self.ev(**self.shield_args(
            phase_started_on=date(2026, 5, 1),
            activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
        ))
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'pas_de_resurrection_a_entree_plafond')

    def test_target_redeclaration_inside_phase_restores_phase_eligibility(self):
        self.assertTrue(p.declaration_eligible_for_phase(
            datetime(2026, 5, 10), date(2026, 5, 1)
        ))

    def test_rupture_has_priority_over_independent_inactivity(self):
        d = self.ev(target_rupture_active=True, independently_inactive=True)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'rupture_active')

    def test_non_finite_price_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 18), last_price=math.nan)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')

    def test_future_target_declaration_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 20), last_price=1.99)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')


class RotterdamCalibrationT(unittest.TestCase):
    def observed_file(self, extra_rows=()):
        rows = [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-20', 0.868), ('2026-05-21', 0.865), ('2026-05-22', 0.859),
            *extra_rows,
        ]
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        tmp.write('date,rotterdam_eur_l\n')
        for d, v in rows:
            tmp.write(f'{d},{v}\n')
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def daily_file(self, rows):
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, suffix='.csv')
        tmp.write('date,rotterdam_eur_l,rotterdam_observed,rotterdam_carried\n')
        for d, value in rows:
            tmp.write(f'{d.isoformat()},{value},True,False\n')
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def meta_file(self, **overrides):
        calibration = {
            'territory': 'corsica',
            'entry_date': '2026-04-08',
            'r1_observation_count': 3,
            'r1': 1.0486666666666666,
            'k': 0.7329942783728567,
            'r2': 0.7686666666666667,
            'r1_source_dates': ['2026-04-03', '2026-04-06', '2026-04-07'],
            'exit_source_dates': ['2026-05-29', '2026-06-01', '2026-06-02'],
        }
        calibration.update(overrides)
        payload = {'rotterdam': {'corsica_calibration': calibration}}
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, suffix='.json')
        json.dump(payload, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_2026_reference_calibrates_corse_k(self):
        c = rc.calibrate_2026('corsica', self.observed_file(), self.meta_file())
        self.assertEqual(c.r1_source_dates, (date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7)))
        self.assertAlmostEqual(c.k, 0.7329942784, places=9)
        self.assertAlmostEqual(c.r2, 0.7686666667, places=9)

    def test_2026_reference_calibrates_bdr_k(self):
        bdr = rc.calibrate_2026('bdr', self.observed_file(), self.meta_file())
        self.assertAlmostEqual(bdr.r1, 1.0486666667, places=9)
        self.assertAlmostEqual(bdr.k, 0.8239033694, places=9)
        self.assertAlmostEqual(bdr.r2, 0.864, places=12)

    def test_new_phase_recomputes_r1_and_r2_but_keeps_k(self):
        observed = self.observed_file(extra_rows=(
            ('2026-09-28', 0.900),
            ('2026-09-29', 0.930),
            ('2026-09-30', 0.960),
        ))
        baseline = rc.calibrate_2026('bdr', observed, self.meta_file())
        phase = rc.calibrate_phase('bdr', date(2026, 10, 1), observed, self.meta_file())
        self.assertEqual(phase.r1_source_dates, (
            date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)
        ))
        self.assertAlmostEqual(phase.r1, 0.930, places=12)
        self.assertAlmostEqual(phase.k, baseline.k, places=12)
        self.assertAlmostEqual(phase.r2, baseline.k * 0.930, places=12)
        self.assertNotAlmostEqual(phase.r2, 0.864, places=6)

    def test_corse_phase_uses_shared_k_with_new_r1(self):
        observed = self.observed_file(extra_rows=(
            ('2026-09-28', 0.900), ('2026-09-29', 0.930), ('2026-09-30', 0.960),
        ))
        phase = rc.calibrate_phase('corsica', date(2026, 10, 1), observed, self.meta_file())
        self.assertAlmostEqual(phase.r1, 0.930, places=12)
        self.assertAlmostEqual(phase.r2, 0.7329942783728567 * 0.930, places=12)

    def test_phase_specific_r2_boundary_is_greater_or_equal(self):
        observed = self.observed_file()
        meta = self.meta_file()
        phase_start = date(2026, 4, 8)
        day = date(2026, 8, 19)
        self.assertTrue(rc.admissible_since(
            day, day, 'corsica', phase_started_on=phase_start,
            observed_file=observed,
            daily_file=self.daily_file([(day, 0.7686666666666667)]), shared_meta_file=meta
        ))
        self.assertFalse(rc.admissible_since(
            day, day, 'corsica', phase_started_on=phase_start,
            observed_file=observed,
            daily_file=self.daily_file([(day, 0.760)]), shared_meta_file=meta
        ))

    def test_r2_breach_stays_locked_even_if_rotterdam_recovers(self):
        observed = self.observed_file()
        meta = self.meta_file()
        start = date(2026, 8, 17)
        rows = [(start, 0.780), (start + timedelta(days=1), 0.760), (start + timedelta(days=2), 0.790)]
        self.assertFalse(rc.admissible_since(
            start, D, 'corsica', phase_started_on=date(2026, 4, 8),
            observed_file=observed, daily_file=self.daily_file(rows), shared_meta_file=meta
        ))

    def test_nonfinite_observed_is_rejected(self):
        with self.assertRaises(ValueError):
            rc.read_observed_csv(self.observed_file(extra_rows=(('2026-04-04', 'nan'),)))

    def test_nonfinite_daily_is_rejected(self):
        with self.assertRaises(ValueError):
            rc.read_daily_values(self.daily_file([(D, 'inf')]))

    def test_invalid_shared_calibration_is_rejected(self):
        with self.assertRaises(ValueError):
            rc.calibrate_2026('corsica', self.observed_file(), self.meta_file(r2=float('nan')))
        with self.assertRaises(ValueError):
            rc.calibrate_2026('corsica', self.observed_file(), self.meta_file(r1_source_dates=['2026-04-04']))

    def test_missing_c1_corse_metadata_fails_closed(self):
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, suffix='.json')
        json.dump({}, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        with self.assertRaises(ValueError):
            rc.calibrate_2026('corsica', self.observed_file(), tmp.name)


if __name__ == '__main__':
    unittest.main()
