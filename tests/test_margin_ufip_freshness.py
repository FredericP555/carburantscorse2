from __future__ import annotations

import unittest

import pandas as pd

from carburantscorse2.publication_margin import (
    contiguous_supported_periods,
    observed_week_is_complete,
)


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

    def test_later_week_cannot_jump_over_missing_week(self):
        first = pd.DataFrame({
            "date": pd.date_range("2026-08-17", "2026-08-23", freq="D"),
            "rotterdam_eur_l": [0.96] * 7,
            "rotterdam_observed": [False] * 7,
        })
        second = pd.DataFrame({
            "date": pd.date_range("2026-08-24", "2026-08-28", freq="D"),
            "rotterdam_eur_l": [0.90, 0.91, 0.92, 0.93, 0.94],
            "rotterdam_observed": [True] * 5,
        })
        df = pd.concat([first, second], ignore_index=True)
        accepted = contiguous_supported_periods(df, ["2026-08-17", "2026-08-24"])
        self.assertEqual(accepted, set())

    def test_two_complete_consecutive_weeks_are_accepted(self):
        df = pd.DataFrame({
            "date": pd.to_datetime([
                "2026-08-17", "2026-08-18", "2026-08-20", "2026-08-21",
                "2026-08-24", "2026-08-25", "2026-08-27", "2026-08-28",
            ]),
            "rotterdam_eur_l": [0.90, 0.91, 0.93, 0.94, 0.95, 0.96, 0.98, 0.99],
            "rotterdam_observed": [True] * 8,
        })
        accepted = contiguous_supported_periods(df, ["2026-08-17", "2026-08-24"])
        self.assertEqual(
            accepted,
            {pd.Timestamp("2026-08-17"), pd.Timestamp("2026-08-24")},
        )


if __name__ == "__main__":
    unittest.main()
