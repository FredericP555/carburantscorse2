from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest

from carburantscorse2 import reliability_policy_v2 as policy


DAY = date(2026, 9, 21)
PHASE_START = date(2026, 6, 1)


def decision(*, fuel="Gazole", age_days=90, is_total=True, shield=True, price=None,
             cap=None, r2=True):
    if price is None:
        price = 2.25 if fuel == "Gazole" else 1.99
    if cap is None:
        cap = 2.25 if fuel == "Gazole" else 1.99
    last = datetime(2026, 9, 21, tzinfo=timezone.utc) - timedelta(days=age_days)
    return policy.evaluate(
        day=DAY,
        region_kind="corsica",
        target_fuel=fuel,
        last_declared_at=last,
        last_price=price,
        latest_price_valid=True,
        target_rupture_active=False,
        independently_inactive=False,
        is_total=is_total,
        shield_effective=shield,
        applicable_cap=cap,
        phase_started_on=PHASE_START,
        activity_by_fuel={},
        gazole_price=2.25,
        gazole_cap=2.25,
        sp95_price=2.10,
        sp95_cap=1.99,
        rotterdam_stale_price_admissible=r2,
    )


class TotalCorsicaShieldNo45DayCutoffTests(unittest.TestCase):
    def test_gazole_total_at_cap_survives_90_days_when_ufip_guard_is_admissible(self):
        self.assertTrue(decision(fuel="Gazole", age_days=90, r2=True).eligible)

    def test_sp95_is_evaluated_independently_from_gazole_cap_state(self):
        self.assertTrue(decision(fuel="SP95", age_days=90, r2=True).eligible)

    def test_45_days_is_not_a_cutoff_for_total_under_effective_shield(self):
        self.assertTrue(decision(fuel="Gazole", age_days=45, r2=True).eligible)

    def test_very_old_total_price_can_remain_valid_under_effective_shield(self):
        self.assertTrue(decision(fuel="Gazole", age_days=180, r2=True).eligible)

    def test_ufip_guard_still_blocks_extension(self):
        self.assertFalse(decision(fuel="Gazole", age_days=90, r2=False).eligible)

    def test_missing_ufip_guard_fails_closed(self):
        self.assertFalse(decision(fuel="Gazole", age_days=90, r2=None).eligible)

    def test_non_total_does_not_get_the_exception(self):
        self.assertFalse(decision(fuel="Gazole", age_days=90, is_total=False, r2=True).eligible)

    def test_price_not_at_cap_does_not_get_the_exception(self):
        self.assertFalse(decision(fuel="Gazole", age_days=90, price=2.24, r2=True).eligible)

    def test_no_effective_shield_means_normal_staleness_rule(self):
        self.assertFalse(decision(fuel="Gazole", age_days=90, shield=False, r2=True).eligible)

    def test_fresh_official_price_remains_valid_without_ufip_extension(self):
        result = decision(fuel="Gazole", age_days=10, r2=None)
        self.assertTrue(result.eligible)
        self.assertEqual(result.reason, "normal_45j")


if __name__ == "__main__":
    unittest.main()
