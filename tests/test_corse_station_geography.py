from __future__ import annotations

import csv
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GEOGRAPHY = ROOT / "config" / "corse_station_geography_2026.csv"


class CorseStationGeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with GEOGRAPHY.open(encoding="utf-8", newline="") as fh:
            cls.rows = list(csv.DictReader(fh))
        cls.by_id = {row["station_id"]: row for row in cls.rows}

    def test_station_ids_are_unique(self):
        ids = [row["station_id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_registry_still_covers_19_epci(self):
        epci = {row["epci_siren"] for row in self.rows if row["epci_siren"]}
        self.assertEqual(len(epci), 19)

    def test_new_september_station_geography_is_explicit(self):
        expected = {
            "20213008": {
                "ville_source": "Penta-di-Casinca",
                "adresse_source": "Avenue de Folelli",
                "localite": "Folelli",
                "commune": "Penta-di-Casinca",
                "confiance": "A",
                "epci_siren": "200073252",
                "epci_nom": "CC de la Castagniccia-Casinca",
                "source_epci": "BANATIC/DGCL",
            },
            "20214003": {
                "ville_source": "Calenzana",
                "adresse_source": "QUARTIER ANNUNZIATA",
                "localite": "Calenzana",
                "commune": "Calenzana",
                "confiance": "C",
                "epci_siren": "242020105",
                "epci_nom": "CC de Calvi Balagne",
                "source_epci": "BANATIC/DGCL",
            },
            "20270004": {
                "ville_source": "Aléria",
                "adresse_source": "T10",
                "localite": "Cateraggio",
                "commune": "Aléria",
                "confiance": "A",
                "epci_siren": "200015162",
                "epci_nom": "CC de l'Oriente",
                "source_epci": "BANATIC/DGCL",
            },
        }
        for station_id, fields in expected.items():
            self.assertIn(station_id, self.by_id)
            row = self.by_id[station_id]
            for key, value in fields.items():
                self.assertEqual(row[key], value, f"{station_id} {key}")


if __name__ == "__main__":
    unittest.main()
