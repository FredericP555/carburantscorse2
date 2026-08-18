from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from a4c_common.official_prices import (
    annual_url,
    deduplicate_daily,
    department_from_cp,
    is_price_in_reference_band,
    iter_observations_from_zip,
)
from a4c_common.ufip import expand_daily, parse_rotterdam_gazole_xlsx
from carburantscorse2.margins import compute_gazole_margin, excise_gazole_eur_l
from carburantscorse2.method import build_daily_series, deduplicate_daily as c2_dedup


class CommonTests(unittest.TestCase):
    def test_annual_url(self):
        today = date(2026, 8, 18)
        self.assertEqual(annual_url(2026, today=today), "https://donnees.roulez-eco.fr/opendata/annee")
        self.assertTrue(annual_url(2025, today=today).endswith("/annee/2025"))

    def test_reference_band(self):
        self.assertTrue(is_price_in_reference_band(1.10))
        self.assertTrue(is_price_in_reference_band(3.00))
        self.assertFalse(is_price_in_reference_band(1.099))
        self.assertFalse(is_price_in_reference_band(None))

    def test_department_from_cp_is_generic_but_keeps_corsica_prefix(self):
        self.assertEqual(department_from_cp("13001"), "13")
        self.assertEqual(department_from_cp("75001"), "75")
        self.assertEqual(department_from_cp("20200"), "20")
        self.assertIsNone(department_from_cp("ABC"))

    def test_common_parser_can_disable_geographic_filter(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<pdv_liste>
  <pdv id="13000001" cp="13001" pop="R"><ville>Marseille</ville><prix nom="Gazole" id="1" maj="2026-08-18T08:00:00" valeur="1.80"/></pdv>
  <pdv id="75000001" cp="75001" pop="R"><ville>Paris</ville><prix nom="Gazole" id="1" maj="2026-08-18T08:00:00" valeur="1.90"/></pdv>
</pdv_liste>'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("PrixCarburants_annuel_2026.xml", xml)
            default_rows = list(iter_observations_from_zip(path))
            all_rows = list(iter_observations_from_zip(path, departments=None))
        self.assertEqual([row["department"] for row in default_rows], ["13"])
        self.assertEqual([row["department"] for row in all_rows], ["13", "75"])

    def test_common_last_declaration_of_day_wins(self):
        rows = [
            {"station_id":"13000001","fuel":"Gazole","date":date(2026,1,2),"timestamp":datetime(2026,1,2,8),"price":1.7},
            {"station_id":"13000001","fuel":"Gazole","date":date(2026,1,2),"timestamp":datetime(2026,1,2,18),"price":1.8},
        ]
        got = deduplicate_daily(rows)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["price"], 1.8)

    def test_ufip_parser_and_forward_fill(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Date", "GAZOLE (Rotterdam) (€ / litre)"])
        ws.append([datetime(2026,8,14), 0.961])
        ws.append([datetime(2026,8,17), 0.973])
        buf = io.BytesIO(); wb.save(buf)
        parsed = parse_rotterdam_gazole_xlsx(buf.getvalue())
        self.assertEqual(parsed.to_dict("records"), [
            {"date": date(2026,8,14), "rotterdam_eur_l": 0.961},
            {"date": date(2026,8,17), "rotterdam_eur_l": 0.973},
        ])
        daily = expand_daily(parsed, date(2026,8,14), date(2026,8,17))
        sat = daily[daily["date"].eq(date(2026,8,15))].iloc[0]
        self.assertAlmostEqual(sat.rotterdam_eur_l, 0.961)
        self.assertTrue(bool(sat.rotterdam_carried))
        mon = daily[daily["date"].eq(date(2026,8,17))].iloc[0]
        self.assertTrue(bool(mon.rotterdam_observed))

    def test_c2_thresholds_follow_recovered_executable_profile(self):
        rows = pd.DataFrame([
            {"station_id":"13000001","department":"13","cp":"13001","city":"M","address":"A","pop":"R","is_motorway":False,"latitude":"","longitude":"","fuel_id":"1","fuel":"Gazole","timestamp":"2026-01-01T08:00:00","date":"2026-01-01","price":1.8},
            {"station_id":"13000001","department":"13","cp":"13001","city":"M","address":"A","pop":"R","is_motorway":False,"latitude":"","longitude":"","fuel_id":"1","fuel":"Gazole","timestamp":"2026-02-10T08:00:00","date":"2026-02-10","price":1.9},
        ])
        dedup = c2_dedup(rows)
        daily = build_daily_series(dedup, global_end=pd.Timestamp("2026-04-15"))
        d31 = daily[daily["date"].eq(pd.Timestamp("2026-02-01"))].iloc[0]
        self.assertTrue(bool(d31.gap_suspect))
        after_last_61 = daily[daily["date"].eq(pd.Timestamp("2026-04-12"))].iloc[0]
        self.assertTrue(bool(after_last_61.station_inactive))

    def test_margin_formula(self):
        self.assertEqual(excise_gazole_eur_l("13", date(2024,12,31)), 0.594)
        self.assertEqual(excise_gazole_eur_l("13", date(2025,1,1)), 0.6075)
        expected = 1.90 / 1.13 - 0.594 - 0.90
        self.assertAlmostEqual(compute_gazole_margin(1.90, "20", date(2026,8,18), 0.90), expected)


if __name__ == "__main__":
    unittest.main()
