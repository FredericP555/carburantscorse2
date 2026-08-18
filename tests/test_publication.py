from __future__ import annotations

import unittest
import pandas as pd

from carburantscorse2.publication import build_publication_state, build_gap_series


def row(station, department, fuel, day, price, hour=12):
    stamp = pd.Timestamp(day) + pd.Timedelta(hours=hour)
    return {
        "station_id": str(station),
        "department": str(department),
        "cp": "13000" if str(department) == "13" else "20000",
        "city": "X",
        "address": "X",
        "pop": "R",
        "is_motorway": False,
        "latitude": "",
        "longitude": "",
        "fuel_id": "1",
        "fuel": fuel,
        "timestamp": stamp,
        "date": stamp.normalize(),
        "price": price,
    }


class PublicationProfileTests(unittest.TestCase):
    def test_bounded_long_gap_marks_the_whole_carried_interval(self):
        df = pd.DataFrame([
            row("13000001", "13", "Gazole", "2026-01-01", 1.80),
            row("13000001", "13", "Gazole", "2026-02-05", 1.90),  # 35-day gap
        ])
        state = build_publication_state(df, global_end=pd.Timestamp("2026-02-05"))
        by_day = state.set_index("date")
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-01-01"), "gap_suspect"]))
        self.assertTrue(bool(by_day.loc[pd.Timestamp("2026-01-02"), "gap_suspect"]))
        self.assertTrue(bool(by_day.loc[pd.Timestamp("2026-02-04"), "gap_suspect"]))
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-02-05"), "gap_suspect"]))

    def test_unbounded_tail_becomes_inactive_only_after_threshold(self):
        df = pd.DataFrame([row("13000001", "13", "Gazole", "2026-01-01", 1.80)])
        state = build_publication_state(df, global_end=pd.Timestamp("2026-02-01"))
        by_day = state.set_index("date")
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-01-31"), "station_inactive"]))
        self.assertTrue(bool(by_day.loc[pd.Timestamp("2026-02-01"), "station_inactive"]))
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-01-31"), "gap_suspect"]))

    def test_last_declaration_of_day_wins(self):
        df = pd.DataFrame([
            row("13000001", "13", "Gazole", "2026-01-01", 1.80, 8),
            row("13000001", "13", "Gazole", "2026-01-01", 1.90, 18),
        ])
        state = build_publication_state(df, global_end=pd.Timestamp("2026-01-01"))
        self.assertAlmostEqual(float(state.iloc[0]["price"]), 1.90)

    def test_aberrant_latest_declaration_is_not_silently_corrected(self):
        df = pd.DataFrame([
            row("13000001", "13", "Gazole", "2026-01-01", 1.80),
            row("13000001", "13", "Gazole", "2026-01-02", 0.50),
            row("13000001", "13", "Gazole", "2026-01-04", 1.85),
        ])
        state = build_publication_state(df, global_end=pd.Timestamp("2026-01-04"))
        by_day = state.set_index("date")
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-01-02"), "eligible_publication"]))
        self.assertFalse(bool(by_day.loc[pd.Timestamp("2026-01-03"), "eligible_publication"]))
        self.assertTrue(bool(by_day.loc[pd.Timestamp("2026-01-04"), "eligible_publication"]))

    def test_station_day_ht_is_rounded_before_aggregation(self):
        rows = []
        for i in range(5):
            rows.append(row(f"20{i:06d}", "20", "Gazole", "2026-01-05", 1.901 + i * 0.001))
        for i in range(10):
            rows.append(row(f"13{i:06d}", "13", "Gazole", "2026-01-05", 1.701 + i * 0.001))
        state = build_publication_state(pd.DataFrame(rows), global_end=pd.Timestamp("2026-01-05"))
        series = build_gap_series(state, corsica_fuel="Gazole", granularity="daily")
        self.assertEqual(len(series), 1)
        corse = state[state["department"].eq("20")]["price_ht"].mean()
        bdr = state[state["department"].eq("13")]["price_ht"].mean()
        self.assertEqual(series[0]["ecart"], round((corse - bdr) * 100, 2))


if __name__ == "__main__":
    unittest.main()
