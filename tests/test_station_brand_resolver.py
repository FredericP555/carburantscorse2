import json
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.resolve_new_bdr_station_brands import (
    classify_brand,
    ids_to_fetch,
    load_registry,
    resolve_from_observations,
    resolved_categories,
)


class StationBrandResolverTests(unittest.TestCase):
    def test_low_cost_major_rules(self):
        self.assertEqual(classify_brand("TotalEnergies Access"), ("gms_lowcost", "lowcost_major"))
        self.assertEqual(classify_brand("Esso Express"), ("gms_lowcost", "lowcost_major"))
        self.assertEqual(classify_brand("Esso"), ("traditionnel", "major_tradi"))
        self.assertEqual(classify_brand("E.Leclerc"), ("gms_lowcost", "gms"))

    def test_unrecognized_brand_fails_closed(self):
        self.assertEqual(classify_brand("Nouvelle enseigne inconnue"), ("inconnu", "inconnu"))

    def test_unverified_known_ids_enter_bounded_reverification_set(self):
        legacy = {"13000001": "gms"}
        registry = {
            "stations": {
                "13999998": {
                    "enseigne": "TotalEnergies",
                    "segment": "traditionnel",
                    "detail": "major_tradi",
                },
                "13999997": {
                    "enseigne": "",
                    "segment": "inconnu",
                    "detail": "inconnu",
                },
            }
        }
        self.assertEqual(
            ids_to_fetch(
                {"13000001", "13999998", "13999997", "13999999"},
                legacy,
                registry,
                today=date(2026, 9, 8),
                reverify_days=90,
                limit=20,
            ),
            ["13000001", "13999997", "13999998", "13999999"],
        )

    def test_new_esso_express_is_resolved_once_and_kept_when_other_known_id_is_fresh(self):
        observations = [
            {"station_id": "13000001", "department": "13", "pop": "R", "is_motorway": False},
            {"station_id": "13999999", "department": "13", "pop": "R", "is_motorway": False},
        ]
        legacy = {"13000001": "gms"}
        calls = []

        def fake_fetch(station_id):
            calls.append(station_id)
            return "Esso Express", None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")
            registry_path.write_text(json.dumps({
                "schema": "a4c-bdr-station-brands-v2",
                "stations": {
                    "13000001": {
                        "enseigne": "E.Leclerc",
                        "segment": "gms_lowcost",
                        "detail": "gms",
                        "classification_source": "auto",
                        "brand_source": "officiel",
                        "first_seen": "2026-09-01",
                        "last_seen": "2026-09-01",
                        "verified_at": "2026-09-01T00:00:00+00:00",
                        "brand_valid_from": "2026-09-01",
                        "brand_history": [],
                    }
                },
            }), encoding="utf-8")

            now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
            first = resolve_from_observations(
                observations,
                legacy,
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=fake_fetch,
                today=date(2026, 9, 8),
                now=now,
            )
            self.assertEqual(first["brand_fetch_count"], 1)
            self.assertEqual(calls, ["13999999"])
            self.assertEqual(first["categories"]["13999999"], "gms")
            saved = load_registry(registry_path)
            self.assertEqual(saved["stations"]["13999999"]["enseigne"], "Esso Express")
            self.assertEqual(saved["stations"]["13999999"]["segment"], "gms_lowcost")
            self.assertEqual(saved["stations"]["13999999"]["detail"], "lowcost_major")

            second = resolve_from_observations(
                observations,
                legacy,
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=fake_fetch,
                today=date(2026, 9, 8),
                now=now,
            )
            self.assertEqual(second["brand_fetch_count"], 0)
            self.assertEqual(calls, ["13999999"])

    def test_unresolved_is_retried_and_not_classified(self):
        observations = [
            {"station_id": "13999996", "department": "13", "pop": "R", "is_motorway": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")

            first = resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: (None, "temporary failure"),
            )
            self.assertEqual(first["unresolved_this_run"], 1)
            self.assertNotIn("13999996", first["categories"])
            saved = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["stations"]["13999996"]["segment"], "inconnu")

            second = resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: ("TotalEnergies", None),
            )
            self.assertEqual(second["brand_fetch_count"], 1)
            self.assertEqual(second["categories"]["13999996"], "network")
            self.assertEqual(resolved_categories(load_registry(registry_path))["13999996"], "network")


if __name__ == "__main__":
    unittest.main()
