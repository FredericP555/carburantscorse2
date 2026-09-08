from __future__ import annotations

from datetime import date
import unittest

import pandas as pd

from a4c_common.shared_release import _validate_rotterdam_contract
from carburantscorse2.publication import build_publication_state
from scripts.build_homepage_summary import _reconcile_gap_series
from scripts.resolve_new_bdr_station_brands import classification_for_day, ids_to_fetch


class TemporalBdrCategoryTests(unittest.TestCase):
    def test_legacy_category_is_frozen_before_temporal_start_and_new_category_applies_after(self):
        legacy = {"13000001": "network"}
        registry = {
            "stations": {
                "13000001": {
                    "enseigne": "Carrefour Market",
                    "segment": "gms_lowcost",
                    "detail": "gms",
                    "brand_source": "officiel",
                    "brand_valid_from": "2026-09-08",
                    "verified_at": "2026-09-08T00:00:00+00:00",
                }
            }
        }
        self.assertEqual(classification_for_day("13000001", date(2026, 9, 7), legacy, registry), "network")
        self.assertEqual(classification_for_day("13000001", date(2026, 9, 8), legacy, registry), "gms")

    def test_known_legacy_id_without_current_verification_is_targeted(self):
        self.assertEqual(
            ids_to_fetch(
                {"13000001"},
                {"13000001": "network"},
                {"stations": {}},
                today=date(2026, 9, 8),
                reverify_days=90,
                limit=20,
            ),
            ["13000001"],
        )

    def test_publication_state_can_change_category_by_date(self):
        observations = pd.DataFrame([
            {"station_id": "13000001", "department": "13", "cp": "13001", "fuel": "Gazole", "timestamp": "2026-09-07T08:00:00", "date": "2026-09-07", "price": 1.90, "is_motorway": False},
            {"station_id": "13000001", "department": "13", "cp": "13001", "fuel": "Gazole", "timestamp": "2026-09-08T08:00:00", "date": "2026-09-08", "price": 1.90, "is_motorway": False},
        ])
        resolver = lambda sid, day: "network" if pd.Timestamp(day).date() <= date(2026, 9, 7) else "gms"
        state = build_publication_state(
            observations,
            global_end=pd.Timestamp("2026-09-08"),
            bdr_category_resolver=resolver,
        )
        categories = dict(zip(state["date"].dt.date, state["category"]))
        self.assertEqual(categories[date(2026, 9, 7)], "network")
        self.assertEqual(categories[date(2026, 9, 8)], "gms")


class HomepageReconciliationTests(unittest.TestCase):
    def test_old_revision_outside_last_two_points_is_reconciled_to_published_json(self):
        data = {
            "DATA": {
                "gazole": {
                    "sp95": {
                        "daily": {
                            "all": [
                                {"date": "2026-08-20", "ecart": 10.00},
                                {"date": "2026-08-21", "ecart": 11.00},
                                {"date": "2026-08-22", "ecart": 12.00},
                            ]
                        }
                    }
                }
            }
        }
        generated = [
            {"date": "2026-08-20", "gap_ht_c_l": 10.06},
            {"date": "2026-08-21", "gap_ht_c_l": 11.00},
            {"date": "2026-08-22", "gap_ht_c_l": 12.00},
        ]
        reconciled, adjustments = _reconcile_gap_series(data, "Gazole", "daily", "all", generated)
        self.assertEqual(reconciled[0]["gap_ht_c_l"], 10.00)
        self.assertEqual(len(adjustments), 1)
        self.assertEqual(adjustments[0]["date"], "2026-08-20")


class RotterdamManifestContractTests(unittest.TestCase):
    def test_rotterdam_contract_requires_unit_source_and_smoothing(self):
        valid = {
            "provider": "UFIP",
            "reference_source": "Thomson-Reuters",
            "unit": "EUR/L",
            "smoothing": "5-day moving average",
            "value_column": "rotterdam_eur_l",
            "single_download": True,
        }
        _validate_rotterdam_contract(valid)
        for field in ("unit", "smoothing", "reference_source"):
            broken = dict(valid)
            broken.pop(field)
            with self.assertRaises(RuntimeError):
                _validate_rotterdam_contract(broken)


if __name__ == "__main__":
    unittest.main()
