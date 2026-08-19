from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
from unittest.mock import patch
import unittest

from a4c_common.shared_release import (
    DATA_ASSET,
    META_ASSET,
    SCHEMA,
    _asset_url,
    _decode_snapshot,
    _request_headers,
    _select_shared_release,
)


class SharedReleaseTests(unittest.TestCase):
    def test_selects_newest_matching_published_release(self):
        releases = [
            {"tag_name": "other-v1", "draft": False, "published_at": "2026-08-19T08:00:00Z"},
            {"tag_name": "a4c-shared-old", "draft": False, "published_at": "2026-08-18T05:00:00Z"},
            {"tag_name": "a4c-shared-draft", "draft": True, "published_at": "2026-08-20T05:00:00Z"},
            {"tag_name": "a4c-shared-new", "draft": False, "published_at": "2026-08-19T05:00:00Z"},
        ]
        self.assertEqual(_select_shared_release(releases)["tag_name"], "a4c-shared-new")

    def test_asset_lookup(self):
        release = {
            "tag_name": "a4c-shared-test",
            "assets": [
                {"name": DATA_ASSET, "browser_download_url": "https://example.test/data"},
                {"name": META_ASSET, "browser_download_url": "https://example.test/meta"},
            ],
        }
        self.assertEqual(_asset_url(release, DATA_ASSET), "https://example.test/data")

    def test_github_token_is_only_sent_to_api_github_com(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=False):
            api_headers = _request_headers("https://api.github.com/repos/x/y/releases")
            asset_headers = _request_headers("https://github.com/x/y/releases/download/tag/data.gz")
        self.assertEqual(api_headers.get("Authorization"), "Bearer test-token")
        self.assertNotIn("Authorization", asset_headers)

    def test_decode_validates_checksum_and_restores_types(self):
        fields = [
            "source_year", "station_id", "department", "cp", "city", "address", "pop",
            "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "timestamp", "date",
            "price", "price_in_reference_band",
        ]
        raw = io.BytesIO()
        with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
            text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
            writer = csv.DictWriter(text, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "source_year": 2026,
                "station_id": "13000001",
                "department": "13",
                "cp": "13001",
                "city": "Marseille",
                "address": "Test",
                "pop": "R",
                "is_motorway": "False",
                "latitude": "",
                "longitude": "",
                "fuel_id": "1",
                "fuel": "Gazole",
                "timestamp": "2026-08-18T08:00:00",
                "date": "2026-08-18",
                "price": "1.8",
                "price_in_reference_band": "True",
            })
            text.flush()
        payload = raw.getvalue()
        meta = {
            "schema": SCHEMA,
            "years": [2025, 2026],
            "departments": ["13", "20"],
            "fuels": ["E10", "Gazole", "SP95"],
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        rows = _decode_snapshot(payload, meta, [2026])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_year"], 2026)
        self.assertEqual(rows[0]["department"], "13")
        self.assertEqual(rows[0]["date"].isoformat(), "2026-08-18")
        self.assertAlmostEqual(rows[0]["price"], 1.8)
        self.assertFalse(rows[0]["is_motorway"])
        self.assertTrue(rows[0]["price_in_reference_band"])

        bad_meta = dict(meta)
        bad_meta["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            _decode_snapshot(payload, bad_meta, [2026])


if __name__ == "__main__":
    unittest.main()
