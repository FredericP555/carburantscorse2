#!/usr/bin/env python3
"""Build a prep-only production preview for the V2 transition.

The preview keeps every published daily value before the switch date untouched and every
weekly value before the first complete Monday-Sunday week after the switch untouched.
From those boundaries onward it rebuilds price-gap series and Gazole apparent margins
from the prospective V2 eligibility state exported by the live dry-run.

This script never writes ``data.json`` and never promotes anything to production.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from carburantscorse2.publication import build_gap_series
from carburantscorse2.publication_margin import build_margin_series

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="outputs/v2/main-data-baseline.json")
    parser.add_argument("--state", default="outputs/v2/v2-prospective-state.csv.gz")
    parser.add_argument("--rotterdam", default="outputs/ufip/rotterdam_gazole_daily.csv")
    parser.add_argument("--switch-date", default="2026-07-23")
    parser.add_argument("--output", default="outputs/v2/production-candidate-preview.json")
    parser.add_argument("--report", default="outputs/v2/production-candidate-diff.json")
    return parser.parse_args()


def first_full_monday(switch_day: date) -> date:
    """First Monday whose complete Monday-Sunday week is entirely on/after switch_day."""
    days_ahead = (7 - switch_day.weekday()) % 7
    if days_ahead == 0:
        return switch_day
    return switch_day + timedelta(days=days_ahead)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_state(path: Path) -> pd.DataFrame:
    state = pd.read_csv(path, low_memory=False)
    required = {
        "station_id", "department", "fuel", "date", "eligible_publication",
        "price_ht", "territory", "category",
    }
    missing = sorted(required - set(state.columns))
    if missing:
        raise RuntimeError(f"Prospective state is missing required columns: {missing}")
    state["station_id"] = state["station_id"].astype(str)
    state["department"] = state["department"].astype(str)
    state["fuel"] = state["fuel"].astype(str)
    state["date"] = pd.to_datetime(state["date"], errors="raise").dt.normalize()
    raw = state["eligible_publication"]
    if raw.dtype != bool:
        state["eligible_publication"] = raw.astype(str).str.lower().isin({"1", "true", "yes"})
    state["price_ht"] = pd.to_numeric(state["price_ht"], errors="coerce")
    return state


def _replace_existing_rows(
    existing: list[dict],
    generated: list[dict],
    *,
    start_on: date,
) -> tuple[list[dict], dict]:
    """Replace only already-published rows dated on/after start_on; never append dates."""
    generated_by_date = {str(row["date"]): dict(row) for row in generated}
    out: list[dict] = []
    changed = 0
    missing_generated: list[str] = []
    max_abs_delta = 0.0
    signed_deltas: list[float] = []

    for row in existing:
        stamp = date.fromisoformat(str(row["date"]))
        if stamp < start_on:
            out.append(deepcopy(row))
            continue
        replacement = generated_by_date.get(str(row["date"]))
        if replacement is None:
            missing_generated.append(str(row["date"]))
            out.append(deepcopy(row))
            continue
        before = deepcopy(row)
        after = deepcopy(replacement)
        out.append(after)
        if before != after:
            changed += 1
            if "ecart" in before and "ecart" in after:
                delta = round(float(after["ecart"]) - float(before["ecart"]), 4)
                signed_deltas.append(delta)
                max_abs_delta = max(max_abs_delta, abs(delta))

    return out, {
        "changed_rows": changed,
        "missing_generated_dates": missing_generated,
        "max_abs_ecart_delta_c_l": round(max_abs_delta, 4),
        "mean_signed_ecart_delta_c_l": (
            round(sum(signed_deltas) / len(signed_deltas), 4) if signed_deltas else 0.0
        ),
    }


def _assert_prefix_exact(before: list[dict], after: list[dict], *, boundary: date, label: str) -> int:
    before_rows = [row for row in before if date.fromisoformat(str(row["date"])) < boundary]
    after_rows = [row for row in after if date.fromisoformat(str(row["date"])) < boundary]
    if before_rows != after_rows:
        raise AssertionError(f"{label}: rows before {boundary.isoformat()} changed")
    return len(before_rows)


def main() -> None:
    args = parse_args()
    baseline_path = ROOT / args.baseline
    state_path = ROOT / args.state
    rotterdam_path = ROOT / args.rotterdam
    output_path = ROOT / args.output
    report_path = ROOT / args.report

    baseline_bytes = baseline_path.read_bytes()
    baseline = json.loads(baseline_bytes.decode("utf-8"))
    candidate = deepcopy(baseline)
    state = _normalize_state(state_path)
    rotterdam = pd.read_csv(rotterdam_path)
    rotterdam["date"] = pd.to_datetime(rotterdam["date"], errors="raise").dt.normalize()
    rotterdam["rotterdam_eur_l"] = pd.to_numeric(rotterdam["rotterdam_eur_l"], errors="coerce")

    switch_day = date.fromisoformat(args.switch_date)
    weekly_switch = first_full_monday(switch_day)

    cases = [
        ("gazole", "sp95", "Gazole", "Gazole"),
        ("sp95", "sp95", "SP95", "SP95"),
        ("sp95", "e10", "SP95", "E10"),
    ]
    series_report: dict[str, dict] = {}
    protected_rows = 0

    for key, ref, corsica_fuel, bdr_fuel in cases:
        for scope, group in (("all", "all"), ("network", "reseau")):
            for granularity in ("daily", "weekly"):
                start_on = switch_day if granularity == "daily" else weekly_switch
                generated = build_gap_series(
                    state,
                    corsica_fuel=corsica_fuel,
                    bdr_fuel=bdr_fuel,
                    bdr_scope=scope,
                    granularity=granularity,
                )
                existing = baseline["DATA"][key][ref][granularity][group]
                replaced, stats = _replace_existing_rows(existing, generated, start_on=start_on)
                protected_rows += _assert_prefix_exact(
                    existing,
                    replaced,
                    boundary=start_on,
                    label=f"DATA/{key}/{ref}/{granularity}/{group}",
                )
                candidate["DATA"][key][ref][granularity][group] = replaced
                series_report[f"DATA/{key}/{ref}/{granularity}/{group}"] = {
                    "transition_start": start_on.isoformat(),
                    **stats,
                }

    margin_state = state[state["date"] >= pd.Timestamp(weekly_switch)].copy()
    for scope, group in (("all", "all"), ("network", "reseau")):
        generated = build_margin_series(margin_state, rotterdam, bdr_scope=scope)
        existing = baseline["MARGES_GZ"][group]
        replaced, stats = _replace_existing_rows(existing, generated, start_on=weekly_switch)
        protected_rows += _assert_prefix_exact(
            existing,
            replaced,
            boundary=weekly_switch,
            label=f"MARGES_GZ/{group}",
        )
        candidate["MARGES_GZ"][group] = replaced
        series_report[f"MARGES_GZ/{group}"] = {
            "transition_start": weekly_switch.isoformat(),
            **stats,
        }

    # Metadata is intentionally additive and preview-only. Existing production metadata is preserved.
    candidate.setdefault("meta", {})["v2_transition_preview"] = {
        "status": "prep-only",
        "production_modified": False,
        "daily_switch_date": switch_day.isoformat(),
        "first_full_week_start": weekly_switch.isoformat(),
        "history_before_switch_preserved": True,
        "weekly_period_overlapping_switch_preserved": True,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_text = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
    output_path.write_text(candidate_text, encoding="utf-8")

    report = {
        "status": "prep-only-production-preview",
        "production_modified": False,
        "baseline": str(baseline_path.relative_to(ROOT)),
        "candidate": str(output_path.relative_to(ROOT)),
        "daily_switch_date": switch_day.isoformat(),
        "weekly_switch_date": weekly_switch.isoformat(),
        "pre_boundary_exact_match": True,
        "protected_rows_verified": protected_rows,
        "baseline_sha256": _sha256_bytes(baseline_bytes),
        "candidate_sha256": _sha256_bytes(candidate_text.encode("utf-8")),
        "series": series_report,
        "changed_rows_total": sum(item["changed_rows"] for item in series_report.values()),
        "missing_generated_dates_total": sum(len(item["missing_generated_dates"]) for item in series_report.values()),
        "notes": [
            "No daily row before 2026-07-23 is changed.",
            "The weekly period starting 2026-07-20 is preserved because it overlaps the switch date.",
            "Only complete weekly periods starting 2026-07-27 or later are rebuilt with V2.",
            "The preview is an artifact only; data.json is not modified.",
        ],
    }
    if report["missing_generated_dates_total"]:
        raise RuntimeError(
            f"Candidate preview is incomplete: {report['missing_generated_dates_total']} published dates have no generated V2 replacement"
        )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
