from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.regression_published_2026 import load_published_reference


class PublishedRegressionSourceTests(unittest.TestCase):
    def test_regression_reference_is_loaded_from_data_json(self):
        payload = {
            "DATA": {"gazole": {"sp95": {"daily": {"all": [{"date": "2026-01-01", "ecart": 1.0}]}}}},
            "MARGES_GZ": {"all": [{"date": "2026-01-05", "ecart": 2.0}]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            data, margins = load_published_reference(path)

        self.assertEqual(data, payload["DATA"])
        self.assertEqual(margins, payload["MARGES_GZ"])

    def test_missing_publication_sections_fail_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"DATA": {}}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_published_reference(path)


if __name__ == "__main__":
    unittest.main()
