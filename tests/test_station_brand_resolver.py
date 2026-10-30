import json
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.resolve_new_bdr_station_brands import (
    classification_for_day,
    classify_brand,
    ids_to_fetch,
    load_corrections,
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

    def test_independent_without_brand_is_explicitly_traditional(self):
        self.assertEqual(
            classify_brand("Indépendant sans enseigne"),
            ("traditionnel", "marque_tradi"),
        )

    def test_dyneff_brand_is_traditional(self):
        self.assertEqual(classify_brand("Dyneff"), ("traditionnel", "major_tradi"))

    def test_historical_brand_missing_from_registry_is_mandatory(self):
        legacy = {"13920010": "network", "13000001": "gms"}
        registry = {"stations": {"13000001": {
            "enseigne": "Intermarché", "segment": "gms_lowcost",
            "verified_at": "2026-10-28T00:00:00Z",
        }}}
        self.assertEqual(
            ids_to_fetch(
                {"13920010", "13000001"}, legacy, registry,
                today=date(2026, 10, 30), limit=0,
            ),
            ["13920010"],
        )

    def test_dyneff_from_official_cache_survives_fetch_failure(self):
        observations = [{
            "station_id": "13130005", "department": "13", "pop": "R",
            "is_motorway": False, "date": date(2026, 10, 12),
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps({
                "schema": "a4c-bdr-station-brands-v2",
                "stations": {"13130005": {
                    "enseigne": "Dyneff", "segment": "inconnu",
                    "detail": "inconnu", "brand_source": "officiel",
                    "first_seen": "2026-09-08", "last_seen": "2026-10-12",
                    "brand_valid_from": "2026-09-08",
                    "verified_at": "2026-10-26T07:00:00Z",
                    "brand_history": [],
                }},
            }), encoding="utf-8")
            result = resolve_from_observations(
                observations, {"13130005": "network"},
                registry_path=path,
                fetcher=lambda _sid: (None, "HTTPError 503"),
                today=date(2026, 10, 30),
                now=datetime(2026, 10, 30, 7, 0, tzinfo=timezone.utc),
            )
            entry = load_registry(path)["stations"]["13130005"]
            self.assertEqual(entry["enseigne"], "Dyneff")
            self.assertEqual(entry["segment"], "traditionnel")
            self.assertEqual(entry["brand_valid_from"], "2026-10-30")
            self.assertEqual(entry["verified_at"], "2026-10-26T07:00:00Z")
            self.assertEqual(result["unresolved_this_run"], 0)
            self.assertEqual(
                classification_for_day("13130005", date(2026, 9, 10),
                                       {"13130005": "network"}, load_registry(path)),
                "network",
            )

    def test_unrecognized_brand_fails_closed(self):
        self.assertEqual(classify_brand("Nouvelle enseigne inconnue"), ("inconnu", "inconnu"))
        self.assertEqual(classify_brand("Proxi"), ("inconnu", "inconnu"))

    def test_proxi_is_corrected_by_station_id_only(self):
        by_id, by_brand = load_corrections()
        self.assertIn("13129001", by_id)
        self.assertEqual(by_id["13129001"]["segment"], "traditionnel")
        self.assertEqual(by_id["13129001"]["detail"], "marque_tradi")
        self.assertIn("Proxi est une enseigne de commerce de proximité", by_id["13129001"]["justification"])
        self.assertNotIn("proxi", by_brand)

        observations = [
            {
                "station_id": "13129001", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 10, 8),
            },
            {
                "station_id": "13360004", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 10, 9),
            },
        ]
        brands = {
            "13129001": "Proxi",
            "13360004": "Indépendant sans enseigne",
        }
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.json"
            result = resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                fetcher=lambda sid: (brands[sid], None),
                today=date(2026, 10, 12),
                now=datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc),
            )
            saved = load_registry(registry_path)

            proxi = saved["stations"]["13129001"]
            self.assertEqual(proxi["segment"], "traditionnel")
            self.assertEqual(proxi["detail"], "marque_tradi")
            self.assertEqual(proxi["classification_source"], "correction_id")
            self.assertEqual(result["categories"]["13129001"], "network")

            independent = saved["stations"]["13360004"]
            self.assertEqual(independent["segment"], "traditionnel")
            self.assertEqual(independent["detail"], "marque_tradi")
            self.assertEqual(independent["classification_source"], "auto")
            self.assertEqual(result["categories"]["13360004"], "network")

    def test_avia_brand_correction_maps_to_traditional_network(self):
        observations = [
            {
                "station_id": "13008018", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 16),
            },
            {
                "station_id": "13008018", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 18),
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text(
                "cle,segment,detail,justification\n"
                "Avia,traditionnel,marque_tradi,Avia appartient au réseau traditionnel\n",
                encoding="utf-8",
            )

            result = resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: ("Avia", None),
                today=date(2026, 9, 21),
                now=datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc),
            )
            saved = load_registry(registry_path)
            entry = saved["stations"]["13008018"]

            self.assertEqual(entry["segment"], "traditionnel")
            self.assertEqual(entry["detail"], "marque_tradi")
            self.assertEqual(entry["classification_source"], "correction_marque")
            self.assertEqual(entry["brand_valid_from"], "2026-09-16")
            self.assertEqual(result["categories"]["13008018"], "network")
            self.assertEqual(
                classification_for_day("13008018", date(2026, 9, 16), {}, saved),
                "network",
            )

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

    def test_new_station_is_valid_from_first_observed_source_date(self):
        observations = [
            {
                "station_id": "13400019", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 18),
            },
            {
                "station_id": "13400019", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 20),
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")

            resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: ("TotalEnergies", None),
                today=date(2026, 9, 21),
                now=datetime(2026, 9, 21, 12, 39, tzinfo=timezone.utc),
            )
            saved = load_registry(registry_path)
            entry = saved["stations"]["13400019"]
            self.assertEqual(entry["first_seen"], "2026-09-18")
            self.assertEqual(entry["last_seen"], "2026-09-20")
            self.assertEqual(entry["brand_valid_from"], "2026-09-18")
            self.assertEqual(
                classification_for_day("13400019", date(2026, 9, 18), {}, saved),
                "network",
            )

    def test_new_station_validity_is_clamped_to_temporal_policy_start(self):
        observations = [
            {
                "station_id": "13999995", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 1),
            },
            {
                "station_id": "13999995", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 3),
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")

            resolve_from_observations(
                observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: ("TotalEnergies", None),
                today=date(2026, 9, 21),
                now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
            )
            saved = load_registry(registry_path)
            entry = saved["stations"]["13999995"]
            self.assertEqual(entry["first_seen"], "2026-09-01")
            self.assertEqual(entry["brand_valid_from"], "2026-09-08")
            self.assertIsNone(
                classification_for_day("13999995", date(2026, 9, 7), {}, saved)
            )
            self.assertEqual(
                classification_for_day("13999995", date(2026, 9, 8), {}, saved),
                "network",
            )

    def test_unresolved_retry_keeps_original_first_observed_date(self):
        first_observations = [
            {
                "station_id": "13999996", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 18),
            },
        ]
        second_observations = [
            *first_observations,
            {
                "station_id": "13999996", "department": "13", "pop": "R",
                "is_motorway": False, "date": date(2026, 9, 21),
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            corrections = root / "corrections.csv"
            corrections.write_text("cle,segment,detail,justification\n", encoding="utf-8")

            resolve_from_observations(
                first_observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: (None, "temporary failure"),
                today=date(2026, 9, 21),
                now=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
            )
            resolve_from_observations(
                second_observations,
                {},
                registry_path=registry_path,
                corrections_path=corrections,
                fetcher=lambda _sid: ("TotalEnergies", None),
                today=date(2026, 9, 22),
                now=datetime(2026, 9, 22, 7, 0, tzinfo=timezone.utc),
            )
            saved = load_registry(registry_path)
            entry = saved["stations"]["13999996"]
            self.assertEqual(entry["first_seen"], "2026-09-18")
            self.assertEqual(entry["last_seen"], "2026-09-21")
            self.assertEqual(entry["brand_valid_from"], "2026-09-18")
            self.assertEqual(entry["segment"], "traditionnel")

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



class HistoricalBackfillTests(unittest.TestCase):
    def test_backfill_looks_beyond_30_days_without_inventing_observations(self):
        from scripts.build_v2_production_candidate import (
            _brand_quality_summary, _historical_unresolved_rows,
        )
        legacy = {"13920010": "network", "13013011": "network",
                  "13130005": "network", "13000001": "gms"}
        registry = {"stations": {
            "13130005": {"enseigne": "Dyneff", "segment": "inconnu"},
            "13000001": {"enseigne": "Intermarché", "segment": "gms_lowcost"},
        }}
        observations = [
            {"station_id": "13920010", "department": "13", "pop": "R",
             "is_motorway": False, "date": date(2026, 9, 24)},
            {"station_id": "13000001", "department": "13", "pop": "R",
             "is_motorway": False, "date": date(2026, 10, 25)},
        ]
        missing, rows = _historical_unresolved_rows(
            observations, legacy, registry, recent_ids={"13000001", "13130005"}
        )
        self.assertEqual(missing, {"13920010", "13013011"})
        self.assertEqual([row["station_id"] for row in rows], ["13920010"])
        audit = _brand_quality_summary(legacy, registry)
        self.assertEqual(audit["missing_enseigne_ids"], ["13013011", "13920010"])
        self.assertEqual(audit["identified_but_unclassified_ids"], ["13130005"])


if __name__ == "__main__":
    unittest.main()
