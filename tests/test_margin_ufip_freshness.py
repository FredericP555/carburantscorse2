from __future__ import annotations

import unittest

import pandas as pd

from carburantscorse2.publication_margin import observed_week_is_complete


class MarginUfipFreshnessTests(unittest.TestCase):
    def test_full_working_week_is_complete(self):
        df = pd.DataFrame({
            "date": pd.date_range("2026-08-17", "2026-08-21", freq="D"),
            "rotterdam_eur_l": [0.90, 0.91, 0.92, 0.93, 0.94],
            "rotterdam_observed": [True] * 5,
        })
        self.assertTrue(observed_week_is_complete(df, "2026-08-17"))

    def test_previous_friday_carried_through_week_is_rejected(self):
        df = pd.DataFrame({
            "date": pd.date_range("2026-08-17", "2026-08-23", freq="D"),
            "rotterdam_eur_l": [0.961] * 7,
            "rotterdam_observed": [False] * 7,
        })
        self.assertFalse(observed_week_is_complete(df, "2026-08-17"))

    def test_monday_holiday_pattern_is_allowed(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]),
            "rotterdam_eur_l": [0.90, 0.91, 0.92, 0.93],
            "rotterdam_observed": [True] * 4,
        })
        self.assertTrue(observed_week_is_complete(df, "2026-08-17"))

    def test_only_early_week_data_is_rejected(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-17", "2026-08-18", "2026-08-19"]),
            "rotterdam_eur_l": [0.90, 0.91, 0.92],
            "rotterdam_observed": [True] * 3,
        })
        self.assertFalse(observed_week_is_complete(df, "2026-08-17"))


if __name__ == "__main__":
    unittest.main()
