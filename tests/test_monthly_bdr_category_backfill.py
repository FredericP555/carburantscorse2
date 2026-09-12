from datetime import date
import unittest

from scripts.monthly_bdr_category_backfill import MonthlyBdrCategoryResolver


class MonthlyBdrCategoryBackfillTests(unittest.TestCase):
    def _registry(self, *, brand="Carrefour Market", segment="gms_lowcost", first_seen="2026-08-31", history=None):
        return {
            "schema": "a4c-bdr-station-brands-v2",
            "stations": {
                "13120012": {
                    "enseigne": brand,
                    "segment": segment,
                    "detail": "gms" if segment == "gms_lowcost" else "major_tradi",
                    "brand_source": "officiel",
                    "classification_source": "auto",
                    "first_seen": first_seen,
                    "verified_at": f"{first_seen}T08:05:56+00:00",
                    "brand_history": history or [],
                }
            },
        }

    def _resolver(self, registry, legacy=None):
        return MonthlyBdrCategoryResolver(
            legacy or {}, registry,
            window_start=date(2026, 8, 1),
            window_end=date(2026, 8, 31),
            max_backfill_days=7,
        )

    def test_same_id_verified_gms_is_backfilled_within_seven_days(self):
        resolver = self._resolver(self._registry())
        for day in range(25, 31):
            self.assertEqual(resolver("13120012", date(2026, 8, day)), "gms")
        self.assertEqual(resolver("13120012", date(2026, 8, 24)), "gms")
        self.assertIsNone(resolver("13120012", date(2026, 8, 23)))
        audit = resolver.audit()
        self.assertEqual(audit["applied_gms_station_days"], 7)
        self.assertEqual(audit["applied_network_station_days"], 0)
        self.assertFalse(audit["policy"]["price_or_eligibility_modified"])

    def test_existing_c2_category_always_wins(self):
        resolver = self._resolver(self._registry(), legacy={"13120012": "network"})
        self.assertEqual(resolver("13120012", date(2026, 8, 25)), "network")
        self.assertEqual(resolver.audit()["applied_station_days"], 0)

    def test_unverified_future_category_is_not_backfilled(self):
        registry = self._registry()
        registry["stations"]["13120012"]["verified_at"] = ""
        resolver = self._resolver(registry)
        self.assertIsNone(resolver("13120012", date(2026, 8, 25)))
        self.assertEqual(resolver.audit()["applied_station_days"], 0)

    def test_conflicting_brand_evidence_blocks_backfill(self):
        history = [{
            "enseigne": "Avia",
            "segment": "inconnu",
            "detail": "inconnu",
            "valid_from": "2026-08-25",
            "valid_to": "2026-08-30",
            "verified_at": "2026-08-25T09:00:00+00:00",
        }]
        resolver = self._resolver(self._registry(history=history))
        self.assertIsNone(resolver("13120012", date(2026, 8, 25)))
        audit = resolver.audit()
        self.assertEqual(audit["applied_station_days"], 0)
        self.assertEqual(len(audit["rejected_conflicts"]), 1)

    def test_same_brand_unknown_history_does_not_create_false_conflict(self):
        history = [{
            "enseigne": "Carrefour Market",
            "segment": "inconnu",
            "detail": "inconnu",
            "valid_from": "2026-08-25",
            "valid_to": "2026-08-30",
            "verified_at": "2026-08-25T09:00:00+00:00",
        }]
        resolver = self._resolver(self._registry(history=history))
        self.assertEqual(resolver("13120012", date(2026, 8, 25)), "gms")
        self.assertEqual(resolver.audit()["applied_station_days"], 1)


if __name__ == "__main__":
    unittest.main()
