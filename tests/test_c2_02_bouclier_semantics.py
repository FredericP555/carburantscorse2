from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def baseline_payload() -> dict:
    return json.loads((ROOT / "data.json").read_text(encoding="utf-8"))


def valid_summary(candidate: dict) -> dict:
    meta = candidate["meta"]
    tag = meta["official_shared_release_tag"]
    return {
        "missing_replacements_total": 0,
        "rewritten_rows_total": 0,
        "added_rows_total": 0,
        "target_end": meta["daily_target_end"],
        "weekly_end": meta["weekly_complete_through"],
        "c1_release_tag": tag,
        "engine": {"r2_unavailable": 0},
        "official_event_guards": {
            "event_rows": 1,
            "reopening_rule": "fixture",
            "release_tag": tag,
        },
    }


def run_preflight(baseline: dict, candidate: dict) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "data.json"
        cand = td / "candidate.json"
        summ = td / "summary.json"
        target.write_text(json.dumps(baseline), encoding="utf-8")
        cand.write_text(json.dumps(candidate), encoding="utf-8")
        summ.write_text(json.dumps(valid_summary(candidate)), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.promote_v2_candidate",
                "--candidate",
                str(cand),
                "--summary",
                str(summ),
                "--target",
                str(target),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )


class C202BouclierSemanticTests(unittest.TestCase):
    def setUp(self):
        self.baseline = baseline_payload()

    def assert_rejected(self, candidate: dict):
        proc = run_preflight(self.baseline, candidate)
        self.assertNotEqual(proc.returncode, 0, msg=f"unexpected success:\n{proc.stdout}\n{proc.stderr}")

    def test_rejects_active_with_empty_ranges_and_phases(self):
        candidate = deepcopy(self.baseline)
        node = candidate["meta"]["bouclier"]["Gazole"]
        node["current_active"] = True
        node["ranges"] = []
        node["phases"] = []
        self.assert_rejected(candidate)

    def test_rejects_phase_cap_99_inside_existing_range(self):
        candidate = deepcopy(self.baseline)
        candidate["meta"]["bouclier"]["Gazole"]["phases"][-1]["cap"] = 99.0
        self.assert_rejected(candidate)

    def test_rejects_phase_outside_effective_ranges(self):
        candidate = deepcopy(self.baseline)
        phase = candidate["meta"]["bouclier"]["SP95"]["phases"][-1]
        phase["d1"] = "1900-01-01"
        phase["d2"] = "1900-01-02"
        self.assert_rejected(candidate)

    def test_inactive_empty_ranges_and_phases_remains_legal(self):
        candidate = deepcopy(self.baseline)
        for fuel in ("Gazole", "SP95"):
            node = candidate["meta"]["bouclier"][fuel]
            node["current_active"] = False
            node["current_active_since"] = None
            node["ranges"] = []
            node["phases"] = []
        proc = run_preflight(self.baseline, candidate)
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
