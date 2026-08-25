from __future__ import annotations

from datetime import date, timedelta
import unittest

import pandas as pd

from scripts.build_homepage_summary import _build_level_series, _comparison_metrics


class HomepageSummaryTests(unittest.TestCase):
    def test_comparison_metrics_week_over_week_four_weeks_and_year(self):
        latest = date(2026, 8, 17)
        rows = []
        for weeks_back in range(60, -1, -1):
            day = latest - timedelta(days=7 * weeks_back)
            rows.append({"date": day.isoformat(), "gap_ht_c_l": float(weeks_back)})
        result = _comparison_metrics(rows)
        self.assertEqual(result["latest"]["date"], "2026-08-17")
        self.assertEqual(result["gap_change_wow_c_l"], -1.0)
        self.assertEqual(result["four_weeks_ago"]["date"], "2026-07-20")
        self.assertEqual(result["gap_change_4w_c_l"], -4.0)
        self.assertEqual(result["year_ago"]["date"], "2025-08-18")
        self.assertEqual(result["gap_change_yoy_c_l"], -52.0)
        self.assertEqual(len(result["recent"]), 8)

    def test_level_series_uses_network_scope_and_all_bdr_guard(self):
        rows = []
        day = pd.Timestamp("2026-08-17")
        for i in range(5):
            rows.append({
                "date": day,
                "eligible_publication": True,
                "territory": "Corse",
                "fuel": "Gazole",
                "category": "network",
                "station_id": f"C{i}",
                "price_ht": 2.0,
                "price": 2.26,
            })
        for i in range(10):
            rows.append({
                "date": day,
                "eligible_publication": True,
                "territory": "Bouches-du-Rhone",
                "fuel": "Gazole",
                "category": "network" if i < 6 else "gms_lowcost",
                "station_id": f"B{i}",
                "price_ht": 1.8 if i < 6 else 1.7,
                "price": 2.16 if i < 6 else 2.04,
            })
        state = pd.DataFrame(rows)
        result = _build_level_series(
            state,
            fuel="Gazole",
            scope="network",
            granularity="daily",
            through=date(2026, 8, 17),
            lookback_days=1,
        )
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row["n_corse"], 5)
        self.assertEqual(row["n_bdr"], 6)
        self.assertEqual(row["n_bdr_guard"], 10)
        self.assertEqual(row["gap_ht_c_l"], 20.0)
        self.assertEqual(row["corse_ttc_eur_l"], 2.26)
        self.assertEqual(row["bdr_ttc_eur_l"], 2.16)


if __name__ == "__main__":
    unittest.main()
