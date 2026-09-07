"""P1 regressions for C2 V2 publication contracts.

Tests are committed before the implementation.  They model two audit findings:
- a recent eligible BDR station with unknown category must block publication;
- a C1 manifest must describe the decoded payload, not only its own checksums.
"""
from __future__ import annotations

import csv
from datetime import date
import gzip
import hashlib
import io
import unittest

import pandas as pd

from a4c_common.shared_release import SCHEMA, _decode_snapshot
from carburantscorse2.publication import validate_recent_bdr_perimeter
from scripts.v2_event_guards import validate_event_manifest


PRICE_FIELDS = [
    "source_year", "station_id", "department", "cp", "city", "address", "pop",
    "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "timestamp", "date",
    "price", "price_in_reference_band",
]
EVENT_FIELDS = [
    "source_year", "station_id", "department", "cp", "city", "address",
    "event_kind", "fuel_id", "fuel", "event_type", "started_at", "ended_at",
    "start_date", "end_date",
]


def gzip_csv(fields, rows):
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        writer = csv.DictWriter(text, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        text.flush()
    return raw.getvalue()


def valid_price_fixture():
    rows = [
        {
            "source_year": "2025", "station_id": "13000001", "department": "13", "cp": "13001",
            "city": "Marseille", "address": "A", "pop": "R", "is_motorway": "False",
            "latitude": "", "longitude": "", "fuel_id": "1", "fuel": "Gazole",
            "timestamp": "2025-12-31T08:00:00", "date": "2025-12-31", "price": "1.8",
            "price_in_reference_band": "True",
        },
        {
            "source_year": "2026", "station_id": "20000001", "department": "20", "cp": "20200",
            "city": "Bastia", "address": "B", "pop": "R", "is_motorway": "False",
            "latitude": "", "longitude": "", "fuel_id": "2", "fuel": "SP95",
            "timestamp": "2026-09-05T08:00:00", "date": "2026-09-05", "price": "1.9",
            "price_in_reference_band": "True",
        },
        {
            "source_year": "2026", "station_id": "13000002", "department": "13", "cp": "13002",
            "city": "Marseille", "address": "C", "pop": "R", "is_motorway": "False",
            "latitude": "", "longitude": "", "fuel_id": "5", "fuel": "E10",
            "timestamp": "2026-09-06T08:00:00", "date": "2026-09-06", "price": "1.7",
            "price_in_reference_band": "True",
        },
    ]
    payload = gzip_csv(PRICE_FIELDS, rows)
    meta = {
        "schema": SCHEMA,
        "years": [2025, 2026],
        "departments": ["13", "20"],
        "fuels": ["E10", "Gazole", "SP95"],
        "rows": 3,
        "min_date": "2025-12-31",
        "max_date": "2026-09-06",
        "rows_by_year": {"2025": 1, "2026": 2},
        "rows_by_department": {"13": 2, "20": 1},
        "rows_by_fuel": {"E10": 1, "Gazole": 1, "SP95": 1},
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    return payload, meta


class SharedManifestSemanticContractTests(unittest.TestCase):
    def test_valid_decoded_payload_matches_manifest(self):
        payload, meta = valid_price_fixture()
        rows = _decode_snapshot(payload, meta, [2026])
        self.assertEqual(len(rows), 2)

    def test_rejects_self_consistent_hash_with_wrong_row_count(self):
        payload, meta = valid_price_fixture()
        meta["rows"] = 999
        with self.assertRaises(RuntimeError):
            _decode_snapshot(payload, meta, [2026])

    def test_rejects_wrong_max_date_even_when_sha_matches(self):
        payload, meta = valid_price_fixture()
        meta["max_date"] = "2026-09-30"
        with self.assertRaises(RuntimeError):
            _decode_snapshot(payload, meta, [2026])

    def test_rejects_wrong_decoded_department_and_fuel_counters(self):
        payload, meta = valid_price_fixture()
        meta["rows_by_department"] = {"13": 1, "20": 2}
        with self.assertRaises(RuntimeError):
            _decode_snapshot(payload, meta, [2026])
        payload, meta = valid_price_fixture()
        meta["rows_by_fuel"] = {"E10": 2, "Gazole": 1, "SP95": 0}
        with self.assertRaises(RuntimeError):
            _decode_snapshot(payload, meta, [2026])


class RecentBdrPerimeterTests(unittest.TestCase):
    def test_unknown_recent_eligible_station_blocks_publication(self):
        state = pd.DataFrame([
            {
                "station_id": "13009999", "territory": "Bouches-du-Rhone",
                "date": pd.Timestamp("2026-09-06"), "eligible_publication": True,
                "category": "unknown",
            }
        ])
        with self.assertRaises(RuntimeError):
            validate_recent_bdr_perimeter(state, since=pd.Timestamp("2026-08-07"))

    def test_known_or_ineligible_station_does_not_block(self):
        state = pd.DataFrame([
            {
                "station_id": "13000001", "territory": "Bouches-du-Rhone",
                "date": pd.Timestamp("2026-09-06"), "eligible_publication": True,
                "category": "network",
            },
            {
                "station_id": "13009999", "territory": "Bouches-du-Rhone",
                "date": pd.Timestamp("2026-09-06"), "eligible_publication": False,
                "category": "unknown",
            },
        ])
        self.assertEqual(validate_recent_bdr_perimeter(state, since=pd.Timestamp("2026-08-07")), [])


class EventManifestSemanticContractTests(unittest.TestCase):
    def test_event_manifest_is_checked_against_decoded_rows(self):
        rows = [
            {
                "source_year": "2026", "station_id": "13000001", "department": "13", "cp": "13001",
                "city": "Marseille", "address": "A", "event_kind": "rupture", "fuel_id": "1",
                "fuel": "Gazole", "event_type": "", "started_at": "2026-08-01T09:00:00",
                "ended_at": "", "start_date": "2026-08-01", "end_date": "",
            },
            {
                "source_year": "2026", "station_id": "20000001", "department": "20", "cp": "20200",
                "city": "Bastia", "address": "B", "event_kind": "fermeture", "fuel_id": "",
                "fuel": "", "event_type": "temporaire", "started_at": "2026-08-02T09:00:00",
                "ended_at": "2026-08-03T09:00:00", "start_date": "2026-08-02", "end_date": "2026-08-03",
            },
        ]
        meta = {
            "rows": 2,
            "rows_by_kind": {"fermeture": 1, "rupture": 1},
            "rows_by_department": {"13": 1, "20": 1},
            "min_start_date": "2026-08-01",
            "max_start_date": "2026-08-02",
        }
        validate_event_manifest(rows, meta)
        bad = dict(meta)
        bad["rows_by_kind"] = {"rupture": 2}
        with self.assertRaises(RuntimeError):
            validate_event_manifest(rows, bad)


if __name__ == "__main__":
    unittest.main()
