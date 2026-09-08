"""Counter-audit regressions for C2-02 and C2-04.

These tests exercise the real ``scripts.promote_v2_candidate`` preflight against a copy
of the repository's canonical ``data.json``. Malformed candidates must fail closed even
if they somehow bypass the production builder.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
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


def run_preflight(baseline: dict, candidate: dict, summary: dict | None = None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "data.json"
        cand = td / "candidate.json"
        summ = td / "summary.json"
        target.write_text(json.dumps(baseline), encoding="utf-8")
        cand.write_text(json.dumps(candidate), encoding="utf-8")
        summ.write_text(json.dumps(summary or valid_summary(candidate)), encoding="utf-8")
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


class C202C204PromotionContractTests(unittest.TestCase):
    def setUp(self):
        self.baseline = baseline_payload()
        self.assertTrue((self.baseline.get("meta") or {}).get("v2", {}).get("active"))

    def assert_rejected(self, candidate: dict, summary: dict | None = None):
        proc = run_preflight(self.baseline, candidate, summary)
        self.assertNotEqual(proc.returncode, 0, msg=f"unexpected success:\n{proc.stdout}\n{proc.stderr}")

    def test_canonical_noop_candidate_passes(self):
        candidate = deepcopy(self.baseline)
        proc = run_preflight(self.baseline, candidate)
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")

    def test_rejects_missing_bouclier_metadata(self):
        candidate = deepcopy(self.baseline)
        candidate["meta"].pop("bouclier", None)
        self.assert_rejected(candidate)

    def test_rejects_missing_bouclier_fuel_nodes(self):
        for fuel in ("Gazole", "SP95"):
            with self.subTest(fuel=fuel):
                candidate = deepcopy(self.baseline)
                candidate["meta"]["bouclier"].pop(fuel, None)
                self.assert_rejected(candidate)

    def test_rejects_missing_bouclier_ranges(self):
        for fuel in ("Gazole", "SP95"):
            with self.subTest(fuel=fuel):
                candidate = deepcopy(self.baseline)
                candidate["meta"]["bouclier"][fuel].pop("ranges", None)
                self.assert_rejected(candidate)

    def test_rejects_daily_point_beyond_declared_source_bound(self):
        candidate = deepcopy(self.baseline)
        candidate["DATA"]["gazole"]["sp95"]["daily"]["all"].append(
            {"date": "2099-01-01", "ecart": 1.0}
        )
        self.assert_rejected(candidate)

    def test_rejects_null_new_gap_even_when_metadata_is_self_consistently_extended(self):
        candidate = deepcopy(self.baseline)
        candidate["DATA"]["gazole"]["sp95"]["daily"]["all"].append(
            {"date": "2099-01-01", "ecart": None}
        )
        candidate["meta"]["daily_target_end"] = "2099-01-01"
        candidate["meta"]["official_source_max_date"] = "2099-01-01"
        candidate["meta"]["official_shared_source_max_date"] = "2099-01-01"
        self.assert_rejected(candidate)

    def test_rejects_daily_target_end_behind_published_daily_series(self):
        candidate = deepcopy(self.baseline)
        candidate["meta"]["daily_target_end"] = date(2026, 7, 23).isoformat()
        self.assert_rejected(candidate)

    def test_rejects_summary_date_metadata_disagreement(self):
        candidate = deepcopy(self.baseline)
        summary = valid_summary(candidate)
        summary["target_end"] = "2099-01-01"
        self.assert_rejected(candidate, summary)


if __name__ == "__main__":
    unittest.main()
