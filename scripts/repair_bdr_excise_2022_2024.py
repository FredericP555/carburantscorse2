#!/usr/bin/env python3
"""One-time guarded repair for C2-01: historic BDR gazole excise, 2022-2024.

The published margin history used 0.5940 EUR/L for Bouches-du-Rhone through
2024. The applicable PACA rate for the public 2022-2024 period is 0.6075
EUR/L, while Corsica remains 0.5940 EUR/L.

This repair is deliberately differential: it does not rebuild historical
prices or Rotterdam quotations from today's sources. It changes only the
published BDR apparent margin and the derived Corsica-minus-BDR margin gap.
The normal V2 append-only promoter remains untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data.json"
DEFAULT_INDEX = ROOT / "index.html"
REPAIR_KEY = "bdr_excise_repair_2022_2024"
FIRST_WEEK = date(2022, 1, 3)
LAST_FULL_WEEK = date(2024, 12, 23)
CROSSOVER_WEEK = date(2024, 12, 30)
BUGGY_BDR_EXCISE_EUR_L = 0.5940
CORRECT_BDR_EXCISE_EUR_L = 0.6075
DELTA_C_L = (CORRECT_BDR_EXCISE_EUR_L - BUGGY_BDR_EXCISE_EUR_L) * 100.0
EXPECTED_FULL_WEEKS = 156
EXPECTED_AFFECTED_WEEKS_PER_GROUP = 157
EXPECTED_CHANGED_ROWS = 314
CROSSOVER_WEIGHTS = {
    "all": {"pre_2025_station_days": 446, "total_station_days": 1603},
    "reseau": {"pre_2025_station_days": 192, "total_station_days": 683},
}
SOURCE_DOCUMENTS = [
    "Douane circulaire 22-008 (2022), annexe 1.1",
    "Douane circulaire 23-022 (2023), annexe 1.1",
    "Douane circulaire 23-031 (2024), annexe 1.1",
]

# These values make the repair fail closed if it is pointed at an unexpected
# historical baseline. They come from the published C2 series audited before
# this migration.
EXPECTED_BASELINE_SAMPLES = {
    ("all", "2023-06-05"): {"ecart": 16.76, "corse": 43.18, "bdr": 26.42},
    ("all", "2024-12-30"): {"ecart": 19.18, "corse": 40.75, "bdr": 21.56},
    ("reseau", "2024-12-30"): {"ecart": 15.53, "corse": 40.75, "bdr": 25.21},
}
EXPECTED_CORRECTED_SAMPLES = {
    ("all", "2023-06-05"): {"ecart": 18.11, "corse": 43.18, "bdr": 25.07},
    ("all", "2024-12-30"): {"ecart": 19.56, "corse": 40.75, "bdr": 21.18},
    ("reseau", "2024-12-30"): {"ecart": 15.91, "corse": 40.75, "bdr": 24.83},
}


def _canonical_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _as_day(row: dict) -> date:
    return date.fromisoformat(str(row["date"]))


def _row_map(payload: dict, group: str) -> dict[str, dict]:
    return {str(row["date"]): row for row in payload["MARGES_GZ"][group]}


def _assert_sample(payload: dict, expected: dict[tuple[str, str], dict]) -> None:
    for (group, day), values in expected.items():
        row = _row_map(payload, group).get(day)
        if row is None:
            raise RuntimeError(f"{group}: required baseline sample {day} is absent")
        for key, wanted in values.items():
            actual = float(row[key])
            if abs(actual - float(wanted)) > 0.00001:
                raise RuntimeError(
                    f"{group}/{day}/{key}: unexpected value {actual}; expected {wanted}"
                )


def _crossover_delta(group: str) -> float:
    weights = CROSSOVER_WEIGHTS[group]
    return DELTA_C_L * weights["pre_2025_station_days"] / weights["total_station_days"]


def _repair_group(rows: list[dict], group: str) -> tuple[list[dict], dict]:
    out = deepcopy(rows)
    original_by_date = {str(r["date"]): deepcopy(r) for r in rows}
    affected = [r for r in out if FIRST_WEEK <= _as_day(r) <= CROSSOVER_WEEK]
    if len(affected) != EXPECTED_AFFECTED_WEEKS_PER_GROUP:
        raise RuntimeError(
            f"{group}: expected {EXPECTED_AFFECTED_WEEKS_PER_GROUP} affected weeks, found {len(affected)}"
        )
    dates = [_as_day(r) for r in affected]
    if dates[0] != FIRST_WEEK or dates[-1] != CROSSOVER_WEEK:
        raise RuntimeError(f"{group}: affected date bounds are not the audited bounds")
    if any(day.weekday() != 0 for day in dates):
        raise RuntimeError(f"{group}: a margin period is not Monday-indexed")
    if any((b - a).days != 7 for a, b in zip(dates, dates[1:])):
        raise RuntimeError(f"{group}: affected margin weeks are not contiguous")

    full_weeks = 0
    changed = 0
    for row in affected:
        day = _as_day(row)
        if day <= LAST_FULL_WEEK:
            delta = DELTA_C_L
            full_weeks += 1
        elif day == CROSSOVER_WEEK:
            delta = _crossover_delta(group)
        else:
            raise RuntimeError(f"{group}: unexpected affected week {day}")

        before_corse = row["corse"]
        row["bdr"] = round(float(row["bdr"]) - delta, 2)
        row["ecart"] = round(float(row["ecart"]) + delta, 2)
        if row["corse"] != before_corse:
            raise RuntimeError(f"{group}/{day}: Corsica margin changed unexpectedly")
        changed += 1

    if full_weeks != EXPECTED_FULL_WEEKS:
        raise RuntimeError(f"{group}: expected {EXPECTED_FULL_WEEKS} full pre-2025 weeks, found {full_weeks}")

    # No 2025+ row may change.
    for row in out:
        if _as_day(row) >= date(2025, 1, 1):
            if row != original_by_date[str(row["date"])]:
                raise RuntimeError(f"{group}/{row['date']}: 2025+ history changed")

    return out, {
        "changed_rows": changed,
        "full_weeks": full_weeks,
        "crossover_delta_c_l_raw": round(_crossover_delta(group), 6),
        "crossover_delta_c_l_published": 0.38,
    }


def build_candidate(payload: dict) -> tuple[dict, dict]:
    meta = payload.get("meta") or {}
    if REPAIR_KEY in meta:
        _assert_sample(payload, EXPECTED_CORRECTED_SAMPLES)
        return deepcopy(payload), {
            "status": "already-applied",
            "repair_key": REPAIR_KEY,
            "changed_rows": 0,
        }

    _assert_sample(payload, EXPECTED_BASELINE_SAMPLES)
    before_data = deepcopy(payload.get("DATA"))
    before_margins_hash = _canonical_hash(payload.get("MARGES_GZ"))
    candidate = deepcopy(payload)
    group_reports = {}
    changed_rows = 0
    for group in ("all", "reseau"):
        repaired, report = _repair_group(candidate["MARGES_GZ"][group], group)
        candidate["MARGES_GZ"][group] = repaired
        group_reports[group] = report
        changed_rows += report["changed_rows"]

    if changed_rows != EXPECTED_CHANGED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_CHANGED_ROWS} changed rows, found {changed_rows}")
    if candidate.get("DATA") != before_data:
        raise RuntimeError("Price-gap DATA changed during the fiscal repair")
    _assert_sample(candidate, EXPECTED_CORRECTED_SAMPLES)

    candidate_meta = candidate.setdefault("meta", {})
    candidate_meta[REPAIR_KEY] = {
        "id": "C2-01",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "reason": "BDR/PACA gazole excise was 0.6075 EUR/L in 2022-2024, not 0.5940 EUR/L",
        "method": "differential correction of published MARGES_GZ only; no historical price or UFIP rebuild",
        "old_bdr_excise_eur_l": BUGGY_BDR_EXCISE_EUR_L,
        "correct_bdr_excise_eur_l": CORRECT_BDR_EXCISE_EUR_L,
        "full_week_delta_c_l": round(DELTA_C_L, 2),
        "first_week": FIRST_WEEK.isoformat(),
        "last_full_week": LAST_FULL_WEEK.isoformat(),
        "crossover_week": CROSSOVER_WEEK.isoformat(),
        "groups": group_reports,
        "changed_rows": changed_rows,
        "margins_sha256_before": before_margins_hash,
        "margins_sha256_after": _canonical_hash(candidate["MARGES_GZ"]),
        "sources": SOURCE_DOCUMENTS,
    }
    report = {
        "status": "candidate-ready",
        "repair_key": REPAIR_KEY,
        "changed_rows": changed_rows,
        "groups": group_reports,
        "margins_sha256_before": before_margins_hash,
        "margins_sha256_after": candidate_meta[REPAIR_KEY]["margins_sha256_after"],
    }
    return candidate, report


def sync_index_fallback(index_text: str, margins: dict) -> str:
    marker = "let MARGES_GZ="
    start = index_text.find(marker)
    if start < 0:
        raise RuntimeError("index.html: mutable MARGES_GZ fallback declaration not found")
    end = index_text.find(";\n", start)
    if end < 0:
        raise RuntimeError("index.html: cannot locate end of MARGES_GZ fallback declaration")
    literal = json.dumps(margins, ensure_ascii=False, separators=(",", ":"))
    updated = index_text[:start] + marker + literal + index_text[end:]
    if updated.count(marker) != 1:
        raise RuntimeError("index.html: expected exactly one MARGES_GZ fallback declaration")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data_path = Path(args.data)
    index_path = Path(args.index)
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    candidate, report = build_candidate(payload)

    if report["status"] == "already-applied":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    index_before = index_path.read_text(encoding="utf-8")
    index_after = sync_index_fallback(index_before, candidate["MARGES_GZ"])
    report["index_fallback_changes"] = 0 if index_after == index_before else 1
    report["production_modified"] = bool(args.apply)

    if args.apply:
        data_path.write_text(
            json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        index_path.write_text(index_after, encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
