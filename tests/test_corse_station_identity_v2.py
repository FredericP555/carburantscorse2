import json
from pathlib import Path
import tempfile
import unittest

from carburantscorse2 import corse_station_identity_v2 as identity


class TestCorsicaStationIdentityV2(unittest.TestCase):
    def registry(self):
        return {
            "schema": identity.EXPECTED_SCHEMA,
            "stations": {
                "1": {"enseigne": "TotalEnergies", "segment": "traditionnel", "brand_source": "officiel"},
                "2": {"enseigne": "VITO", "segment": "traditionnel", "brand_source": "officiel"},
                "3": {"enseigne": "", "segment": "inconnu", "brand_source": "non_resolu"},
                "4": {"enseigne": "Total Access", "segment": "traditionnel", "brand_source": "officiel"},
                "5": {"enseigne": "TotalEnergies Bastia", "segment": "traditionnel", "brand_source": "officiel"},
                "6": {"enseigne": "VITO", "segment": "traditionnel", "brand_source": "NON_RESOLU"},
                "7": {"enseigne": "VITO", "segment": "traditionnel", "brand_source": "non-résolu"},
                "8": {"enseigne": "VITO", "segment": "traditionnel", "brand_source": "unresolved"},
            },
        }

    def test_total(self):
        self.assertEqual(identity.classify_station_id("1", self.registry()), identity.TOTAL)

    def test_total_variants(self):
        self.assertEqual(identity.classify_station_id("4", self.registry()), identity.TOTAL)
        self.assertEqual(identity.classify_station_id("5", self.registry()), identity.TOTAL)

    def test_confirmed_non_total(self):
        self.assertEqual(identity.classify_station_id("2", self.registry()), identity.NON_TOTAL_CONFIRMED)

    def test_unresolved_variants_are_unknown(self):
        for station_id in ("3", "6", "7", "8"):
            self.assertEqual(identity.classify_station_id(station_id, self.registry()), identity.UNKNOWN)

    def test_new_missing_id_is_unknown(self):
        self.assertEqual(identity.classify_station_id("999", self.registry()), identity.UNKNOWN)

    def test_file_schema_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            payload = self.registry()
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(identity.classify_from_file("2", path), identity.NON_TOTAL_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
