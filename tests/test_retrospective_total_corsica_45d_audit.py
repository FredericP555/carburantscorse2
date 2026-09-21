from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest

from scripts.audit_total_corsica_45d_retrospective import legacy_evaluate


DAY = date(2026, 9, 20)


def legacy(*, fuel="SP95", age=90, price=1.99, cap=1.99, other_price=2.25,
           other_cap=2.25, r2=False, activity=None, is_total=True, shield=True,
           phase_start=date(2026, 4, 8)):
    last = datetime(2026, 9, 20, tzinfo=timezone.utc) - timedelta(days=age)
    return legacy_evaluate(
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
        phase_started_on=phase_start,
        activity_by_fuel=activity or {},
        gazole_price=other_price if fuel == "SP95" else price,
        gazole_cap=other_cap if fuel == "SP95" else cap,
        sp95_price=price if fuel == "SP95" else other_price,
        sp95_cap=cap if fuel == "SP95" else other_cap,
        rotterdam_stale_price_admissible=r2,
    )


class LegacyRetrospectivePolicyTests(unittest.TestCase):
    def test_legacy_double_cap_can_be_blocked_by_rotterdam(self):
        result = legacy(
            fuel="SP95",
            age=90,
            price=1.99,
            cap=1.99,
            other_price=2.25,
            other_cap=2.25,
            r2=False,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason, "double_plafond_rotterdam_verrouille")

    def test_legacy_single_cap_can_survive_with_recent_other_principal_fuel(self):
        activity = {"Gazole": datetime(2026, 9, 10, tzinfo=timezone.utc)}
        result = legacy(
            fuel="SP95",
            age=90,
            price=1.99,
            cap=1.99,
            other_price=2.30,
            other_cap=2.25,
            r2=None,
            activity=activity,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.reason, "bouclier_vivacite_45j_renouvelee")

    def test_legacy_single_cap_without_recent_liveness_is_rejected(self):
        result = legacy(
            fuel="SP95",
            age=90,
            price=1.99,
            cap=1.99,
            other_price=2.30,
            other_cap=2.25,
            r2=None,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason, "bouclier_sans_vivacite_recente")

    def test_legacy_never_resurrects_price_already_stale_at_phase_entry(self):
        result = legacy(
            fuel="SP95",
            age=180,
            phase_start=date(2026, 8, 1),
            r2=True,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason, "pas_de_resurrection_a_entree_plafond")

    def test_legacy_fresh_price_remains_normal(self):
        result = legacy(fuel="SP95", age=10, r2=None)
        self.assertTrue(result.eligible)
        self.assertEqual(result.reason, "normal_45j")


if __name__ == "__main__":
    unittest.main()
