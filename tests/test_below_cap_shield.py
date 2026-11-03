"""Ceiling protection covers lower Total prices without bypassing the guards."""
from datetime import date, datetime
from pathlib import Path
import importlib.util, sys, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from a4c_common.price_math import at_cap, at_or_below_cap


def load_policy(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


POLICY = load_policy('below_cap_policy', 'carburantscorse2/reliability_policy_v2.py')


class ShieldPriceTests(unittest.TestCase):
    def args(self, **changes):
        args = dict(day=date(2026, 11, 2), region_kind='corsica', target_fuel='Gazole',
                    last_declared_at=datetime(2026, 9, 16), last_price=2.199,
                    is_total=True, shield_effective=True, applicable_cap=2.25,
                    phase_started_on=date(2026, 7, 23), rotterdam_stale_price_admissible=True)
        args.update(changes)
        return args

    def test_ceiling_comparison_does_not_change_cap_detection(self):
        self.assertTrue(at_or_below_cap(2.199, 2.25))
        self.assertFalse(at_cap(2.199, 2.25))
        self.assertTrue(at_or_below_cap(2.251, 2.25))
        for price in (2.252, 0, -1, None, float('nan'), float('inf')):
            self.assertFalse(at_or_below_cap(price, 2.25))
        self.assertFalse(at_or_below_cap(2.199, None))

    def test_lower_corsica_prices_for_each_fuel(self):
        for policy in (POLICY,):
            for fuel, price, cap in (('Gazole', 2.199, 2.25), ('Gazole', 2.195, 2.25),
                                     ('SP95', 1.959, 1.99), ('SP95', 1.955, 1.99)):
                with self.subTest(policy=policy.__name__, fuel=fuel, price=price):
                    result = policy.evaluate(**self.args(target_fuel=fuel, last_price=price, applicable_cap=cap))
                    self.assertTrue(result.eligible)
                    self.assertEqual(result.reason, 'bouclier_total_ufip_admissible')

    def test_old_lower_prices_still_require_every_other_guard(self):
        cases = [dict(rotterdam_stale_price_admissible=False),
                 dict(rotterdam_stale_price_admissible=None), dict(is_total=False),
                 dict(shield_effective=False), dict(target_rupture_active=True),
                 dict(independently_inactive=True), dict(latest_price_valid=False),
                 dict(last_price=2.26), dict(phase_started_on=None),
                 dict(phase_started_on=date(2026, 11, 3)),
                 dict(last_declared_at=datetime(2026, 1, 1)), dict(applicable_cap=None)]
        for policy in (POLICY,):
            for changes in cases:
                with self.subTest(policy=policy.__name__, changes=changes):
                    self.assertFalse(policy.evaluate(**self.args(**changes)).eligible)

    def test_bdr_lower_prices_keep_nonprincipal_activity_and_r2_requirements(self):
        args = self.args(region_kind='mainland', gazole_price=2.199, gazole_cap=2.25,
                         sp95_price=1.959, sp95_cap=1.99)
        self.assertFalse(POLICY.evaluate(**args).eligible)
        args['activity_by_fuel'] = {'E10': datetime(2026, 11, 1)}
        self.assertTrue(POLICY.evaluate(**args).eligible)
        for verdict in (False, None):
            args['rotterdam_stale_price_admissible'] = verdict
            self.assertFalse(POLICY.evaluate(**args).eligible)

    def test_fresh_prices_and_existing_cap_prices_remain_supported(self):
        for policy in (POLICY,):
            self.assertTrue(policy.evaluate(**self.args(last_price=2.25)).eligible)
            result = policy.evaluate(**self.args(last_declared_at=datetime(2026, 11, 1),
                                                 rotterdam_stale_price_admissible=None,
                                                 shield_effective=False))
            self.assertTrue(result.eligible)
            self.assertEqual(result.reason, 'normal_45j')


if __name__ == '__main__':
    unittest.main()
