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
            last_declared_at=datetime(2026, 1, 1),
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
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_stale_price_admissible=False,
        ))
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_verrouille')

    def test_corse_double_cap_r2_admissible(self):
        d = self.ev(**self.shield_args(
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_stale_price_admissible=True,
        ))
        self.assertTrue(d.eligible)
        self.assertEqual(d.reason, 'double_plafond_rotterdam_admissible')

    def test_bdr_double_cap_requires_nonprincipal_liveness(self):
        d = self.ev(
            region_kind='mainland',
            **self.shield_args(
                activity_by_fuel={'Gazole': datetime(2026, 8, 18)},
                gazole_price=2.25,
                gazole_cap=2.25,
                sp95_price=1.99,
                sp95_cap=1.99,
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
                gazole_price=2.25,
                gazole_cap=2.25,
                sp95_price=1.99,
                sp95_cap=1.99,
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

    def test_inactive_overrides(self):
        d = self.ev(**self.shield_args(
            independently_inactive=True,
            gazole_price=2.25,
            gazole_cap=2.25,
            sp95_price=1.99,
            sp95_cap=1.99,
            rotterdam_stale_price_admissible=True,
        ))
        self.assertFalse(d.eligible)

    def test_non_finite_price_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 18), last_price=math.nan)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')

    def test_future_target_declaration_is_rejected(self):
        d = self.ev(last_declared_at=datetime(2026, 8, 20), last_price=1.99)
        self.assertFalse(d.eligible)
        self.assertEqual(d.reason, 'prix_ou_date_absent_invalide')


class RotterdamCalibrationT(unittest.TestCase):
    def observed_file(self):
        rows = [
            ('2026-04-03', 1.037), ('2026-04-06', 1.048), ('2026-04-07', 1.061),
            ('2026-05-20', 0.868), ('2026-05-21', 0.865), ('2026-05-22', 0.859),
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

    def meta_file(self):
        payload = {
            'rotterdam': {
                'corsica_calibration': {
                    'territory': 'corsica',
                    'entry_date': '2026-04-08',
                    'r1_observation_count': 3,
                    'r1': 1.0486666666666666,
                    'k': 0.7329942783728567,
                    'r2': 0.7686666666666667,
                    'r1_source_dates': ['2026-04-03', '2026-04-06', '2026-04-07'],
                    'exit_source_dates': ['2026-05-29', '2026-06-01', '2026-06-02'],
                }
            }
        }
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, suffix='.json')
        json.dump(payload, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_corse_is_consumed_from_c1_metadata(self):
        c = rc.calibrate_2026('corsica', self.observed_file(), self.meta_file())
        self.assertEqual(c.r1_source_dates, (date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7)))
        self.assertAlmostEqual(c.k, 0.7329942784, places=9)
        self.assertAlmostEqual(c.r2, 0.7686666667, places=9)

    def test_bdr_is_derived_from_shared_observed_csv(self):
        bdr = rc.calibrate_2026('bdr', self.observed_file(), self.meta_file())
        self.assertAlmostEqual(bdr.r1, 1.0486666667, places=9)
        self.assertAlmostEqual(bdr.k, 0.8239033694, places=9)

    def test_r2_comparator_is_greater_or_equal(self):
        observed = self.observed_file()
        meta = self.meta_file()
        self.assertTrue(rc.constraining_on(
            D, 'corsica', observed_file=observed,
            daily_file=self.daily_file([(D, 0.769)]), shared_meta_file=meta
        ))
        self.assertFalse(rc.constraining_on(
            D, 'corsica', observed_file=observed,
            daily_file=self.daily_file([(D, 0.760)]), shared_meta_file=meta
        ))

    def test_r2_breach_stays_locked_even_if_rotterdam_recovers(self):
        observed = self.observed_file()
        meta = self.meta_file()
        start = date(2026, 8, 17)
        rows = [
            (start, 0.780),
            (start + timedelta(days=1), 0.760),
            (start + timedelta(days=2), 0.790),
        ]
        daily = self.daily_file(rows)
        self.assertFalse(rc.admissible_since(
            start, D, 'corsica', observed_file=observed, daily_file=daily, shared_meta_file=meta
        ))

    def test_missing_c1_corse_metadata_fails_closed(self):
        tmp = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, suffix='.json')
        json.dump({}, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        with self.assertRaises(ValueError):
            rc.calibrate_2026('corsica', self.observed_file(), tmp.name)


if __name__ == '__main__':
    unittest.main()
