from __future__ import annotations

import csv
from datetime import datetime
import gzip
import hashlib
import io
import unittest
from zoneinfo import ZoneInfo

import pandas as pd

from a4c_common.shared_release import SCHEMA, _decode_snapshot
from carburantscorse2.publication import build_gap_series, build_publication_state
from scripts.build_append_candidate import default_requested_end, official_year_window


FIELDS = [
    "source_year", "station_id", "department", "cp", "city", "address", "pop",
    "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "timestamp", "date",
    "price", "price_in_reference_band",
]


def snapshot_payload() -> tuple[bytes, dict]:
    rows: list[dict] = []

    # Five Corsica stations and ten BDR stations satisfy the published minimum sample.
    for i in range(5):
        station = f"20{i:06d}"
        rows.extend([
            {
                "source_year": 2026,
                "station_id": station,
                "department": "20",
                "cp": "20000",
                "city": "Ajaccio",
                "address": "Test",
                "pop": "R",
                "is_motorway": "False",
                "latitude": "",
                "longitude": "",
                "fuel_id": "1",
                "fuel": "Gazole",
                "timestamp": "2026-12-31T12:00:00",
                "date": "2026-12-31",
                "price": "1.90",
                "price_in_reference_band": "True",
            },
            {
                "source_year": 2027,
                "station_id": station,
                "department": "20",
                "cp": "20000",
                "city": "Ajaccio",
                "address": "Test",
                "pop": "R",
                "is_motorway": "False",
                "latitude": "",
                "longitude": "",
                "fuel_id": "1",
                "fuel": "Gazole",
                "timestamp": "2027-01-02T12:00:00",
                "date": "2027-01-02",
                "price": "1.95",
                "price_in_reference_band": "True",
            },
        ])

    for i in range(10):
        station = f"13{i:06d}"
        rows.extend([
            {
                "source_year": 2026,
                "station_id": station,
                "department": "13",
                "cp": "13000",
                "city": "Marseille",
                "address": "Test",
                "pop": "R",
                "is_motorway": "False",
                "latitude": "",
                "longitude": "",
                "fuel_id": "1",
                "fuel": "Gazole",
                "timestamp": "2026-12-31T12:00:00",
                "date": "2026-12-31",
                "price": "1.80",
                "price_in_reference_band": "True",
            },
            {
                "source_year": 2027,
                "station_id": station,
                "department": "13",
                "cp": "13000",
                "city": "Marseille",
                "address": "Test",
                "pop": "R",
                "is_motorway": "False",
                "latitude": "",
                "longitude": "",
                "fuel_id": "1",
                "fuel": "Gazole",
                "timestamp": "2027-01-02T12:00:00",
                "date": "2027-01-02",
                "price": "1.80",
                "price_in_reference_band": "True",
            },
        ])

    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    payload = gzip.compress(text.getvalue().encode("utf-8"))
    meta = {
        "schema": SCHEMA,
        "years": [2026, 2027],
        "departments": ["13", "20"],
        "fuels": ["E10", "Gazole", "SP95"],
        "rows": len(rows),
        "max_date": "2027-01-02",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    return payload, meta


class YearBoundaryEndToEndTests(unittest.TestCase):
    def test_january_run_requests_previous_and_current_year(self):
        self.assertEqual(official_year_window(pd.Timestamp("2026-12-31")), (2025, 2026))
        self.assertEqual(official_year_window(pd.Timestamp("2027-01-01")), (2026, 2027))
        self.assertEqual(official_year_window(pd.Timestamp("2027-01-03")), (2026, 2027))

    def test_real_january_first_clock_matches_c1_snapshot_window(self):
        run = datetime(2027, 1, 1, 7, 40, tzinfo=ZoneInfo("Europe/Paris"))
        requested_end = default_requested_end(run)
        self.assertEqual(requested_end, pd.Timestamp("2026-12-31"))
        self.assertEqual(
            official_year_window(requested_end, run_day=pd.Timestamp(run.date())),
            (2026, 2027),
        )

    def test_shared_snapshot_carries_december_state_into_january(self):
        payload, meta = snapshot_payload()
        rows = _decode_snapshot(payload, meta, [2026, 2027])
        self.assertEqual({row["source_year"] for row in rows}, {2026, 2027})

        state = build_publication_state(
            pd.DataFrame(rows),
            global_end=pd.Timestamp("2027-01-03"),
        )
        series = build_gap_series(
            state,
            corsica_fuel="Gazole",
            bdr_fuel="Gazole",
            bdr_scope="all",
            granularity="daily",
        )
        by_date = {row["date"]: row["ecart"] for row in series}

        self.assertEqual(
            list(by_date),
            ["2026-12-31", "2027-01-01", "2027-01-02", "2027-01-03"],
        )
        # 1 January has no declaration: it must inherit the valid 31 December state.
        self.assertEqual(by_date["2027-01-01"], by_date["2026-12-31"])
        # New-year declarations on 2 January must then take over normally.
        self.assertNotEqual(by_date["2027-01-02"], by_date["2027-01-01"])
        self.assertEqual(by_date["2027-01-03"], by_date["2027-01-02"])

    def test_missing_previous_year_is_rejected(self):
        payload, meta = snapshot_payload()
        broken = dict(meta)
        broken["years"] = [2027]
        with self.assertRaisesRegex(RuntimeError, "do not cover"):
            _decode_snapshot(payload, broken, [2026, 2027])


if __name__ == "__main__":
    unittest.main()
