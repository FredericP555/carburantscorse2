from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unittest

from scripts.build_total_corsica_45d_historical_correction import (
    _assert_only_allowed_changes,
    _correct_series,
)


ROOT = Path(__file__).resolve().parents[1]


def baseline_payload() -> dict:
    return json.loads((ROOT / "data.json").read_text(encoding="utf-8"))


class HistoricalCorrectionScopeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = baseline_payload()

    def test_isolated_delta_changes_only_sp95_target_gap_series(self):
        candidate = deepcopy(self.baseline)
        daily_delta = {"2026-09-20": -1.2345}
        weekly_delta = {"2026-09-14": -1.2345}
        old_gazole = deepcopy(candidate["DATA"]["gazole"])
        old_margins = deepcopy(candidate["MARGES_GZ"])

        daily_changes, weekly_changes = _correct_series(
            candidate,
            daily_delta=daily_delta,
            weekly_delta=weekly_delta,
            end=date(2026, 9, 20),
            weekly_end=date(2026, 9, 20),
        )

        self.assertEqual(candidate["DATA"]["gazole"], old_gazole)
        self.assertEqual(candidate["MARGES_GZ"], old_margins)
        self.assertEqual(len(daily_changes), 4)
        self.assertEqual(len(weekly_changes), 4)
        _assert_only_allowed_changes(self.baseline, candidate)

    def test_pre_switch_history_is_never_changed(self):
        candidate = deepcopy(self.baseline)
        _correct_series(
            candidate,
            daily_delta={"2026-07-22": -10.0},
            weekly_delta={"2026-07-20": -10.0},
            end=date(2026, 9, 20),
            weekly_end=date(2026, 9, 20),
        )
        self.assertEqual(candidate, self.baseline)

    def test_scope_guard_rejects_gazole_change(self):
        candidate = deepcopy(self.baseline)
        candidate["DATA"]["gazole"]["sp95"]["daily"]["all"][-1]["ecart"] += 0.01
        with self.assertRaisesRegex(RuntimeError, "Gazole public history changed"):
            _assert_only_allowed_changes(self.baseline, candidate)

    def test_scope_guard_rejects_non_ecart_field_change(self):
        candidate = deepcopy(self.baseline)
        row = candidate["DATA"]["sp95"]["sp95"]["daily"]["all"][-1]
        row["unexpected"] = "no"
        with self.assertRaisesRegex(RuntimeError, "Row shape changed"):
            _assert_only_allowed_changes(self.baseline, candidate)


if __name__ == "__main__":
    unittest.main()
