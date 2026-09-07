from __future__ import annotations

from datetime import date, timedelta
import unittest

from scripts.repair_bdr_excise_2022_2024 import (
    CROSSOVER_WEEK,
    EXPECTED_CHANGED_ROWS,
    REPAIR_KEY,
    build_candidate,
    sync_index_fallback,
)


def _weekly_rows(group: str) -> list[dict]:
    rows = []
    day = date(2022, 1, 3)
    end = date(2025, 1, 6)
    while day <= end:
        row = {"date": day.isoformat(), "ecart": 10.0, "corse": 40.0, "bdr": 30.0}
        if group == "all" and day == date(2023, 6, 5):
            row = {"date": day.isoformat(), "ecart": 16.76, "corse": 43.18, "bdr": 26.42}
        if day == CROSSOVER_WEEK:
            if group == "all":
                row = {"date": day.isoformat(), "ecart": 19.18, "corse": 40.75, "bdr": 21.56}
            else:
                row = {"date": day.isoformat(), "ecart": 15.53, "corse": 40.75, "bdr": 25.21}
        rows.append(row)
        day += timedelta(days=7)
    return rows


class BdrExciseRepairTests(unittest.TestCase):
    def _payload(self):
        return {
            "meta": {},
            "DATA": {"sentinel": {"unchanged": True}},
            "MARGES_GZ": {
                "all": _weekly_rows("all"),
                "reseau": _weekly_rows("reseau"),
            },
        }

    def test_build_candidate_changes_only_audited_margin_history(self):
        payload = self._payload()
        original_2025 = {
            group: [dict(r) for r in payload["MARGES_GZ"][group] if r["date"] >= "2025-01-01"]
            for group in ("all", "reseau")
        }
        candidate, report = build_candidate(payload)

        self.assertEqual(report["changed_rows"], EXPECTED_CHANGED_ROWS)
        self.assertEqual(candidate["DATA"], payload["DATA"])
        self.assertIn(REPAIR_KEY, candidate["meta"])
        self.assertEqual(candidate["meta"][REPAIR_KEY]["changed_rows"], EXPECTED_CHANGED_ROWS)

        all_by_date = {r["date"]: r for r in candidate["MARGES_GZ"]["all"]}
        net_by_date = {r["date"]: r for r in candidate["MARGES_GZ"]["reseau"]}
        self.assertEqual(
            all_by_date["2023-06-05"],
            {"date": "2023-06-05", "ecart": 18.11, "corse": 43.18, "bdr": 25.07},
        )
        self.assertEqual(
            all_by_date["2024-12-30"],
            {"date": "2024-12-30", "ecart": 19.56, "corse": 40.75, "bdr": 21.18},
        )
        self.assertEqual(
            net_by_date["2024-12-30"],
            {"date": "2024-12-30", "ecart": 15.91, "corse": 40.75, "bdr": 24.83},
        )

        for group in ("all", "reseau"):
            after_2025 = [r for r in candidate["MARGES_GZ"][group] if r["date"] >= "2025-01-01"]
            self.assertEqual(after_2025, original_2025[group])

    def test_repair_is_idempotent_after_metadata_is_present(self):
        candidate, _ = build_candidate(self._payload())
        second, report = build_candidate(candidate)
        self.assertEqual(report["status"], "already-applied")
        self.assertEqual(second, candidate)

    def test_index_fallback_is_replaced_without_touching_other_js(self):
        html = "before\nlet MARGES_GZ={old:true};\nafter\n"
        margins = {"all": [{"date": "2024-12-30", "ecart": 19.56}], "reseau": []}
        updated = sync_index_fallback(html, margins)
        self.assertIn('let MARGES_GZ={"all":[{"date":"2024-12-30","ecart":19.56}],"reseau":[]};', updated)
        self.assertTrue(updated.startswith("before\n"))
        self.assertTrue(updated.endswith("after\n"))


if __name__ == "__main__":
    unittest.main()
