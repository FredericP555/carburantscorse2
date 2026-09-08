#!/usr/bin/env python3
"""Verify and optionally promote the controlled A4C V2 production candidate.

Without --promote this is a strict read-only preflight. With --promote it writes the
already-verified candidate bytes to data.json. Initial activation permits rewrites only
from 2026-07-23 daily / 2026-07-27 weekly+margin. Every later V2 run is append-only.

The promoter is the final publication boundary. It therefore validates not only history
preservation but also the public C1 shield contract, candidate date/value bounds and the
visible metadata that describes the publication cutoff.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import math
from pathlib import Path

try:
    from scripts import c2_bouclier_contract
except ImportError:  # direct execution as python scripts/promote_v2_candidate.py
    import c2_bouclier_contract

ROOT = Path(__file__).resolve().parents[1]
DAILY_SWITCH = date(2026, 7, 23)
WEEKLY_SWITCH = date(2026, 7, 27)


def _fail(message: str) -> None:
    raise SystemExit(f"Refusing V2 candidate: {message}")


def _as_date(value, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Refusing V2 candidate: invalid {label}={value!r}") from exc


def _finite(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Refusing V2 candidate: non-numeric {label}={value!r}") from exc
    if not math.isfinite(number):
        _fail(f"non-finite {label}={value!r}")
    return number


def _last_complete_sunday(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def iter_series(obj: dict):
    data = obj.get("DATA")
    margins = obj.get("MARGES_GZ")
    if not isinstance(data, dict) or not isinstance(margins, dict):
        _fail("missing DATA or MARGES_GZ public structure")
    for key, refs in data.items():
        if not isinstance(refs, dict):
            _fail(f"DATA/{key} is not an object")
        for ref, grans in refs.items():
            if not isinstance(grans, dict):
                _fail(f"DATA/{key}/{ref} is not an object")
            for gran, groups in grans.items():
                if gran not in {"daily", "weekly"} or not isinstance(groups, dict):
                    _fail(f"invalid granularity at DATA/{key}/{ref}/{gran}")
                for group, rows in groups.items():
                    if not isinstance(rows, list):
                        _fail(f"DATA/{key}/{ref}/{gran}/{group} is not a list")
                    boundary = DAILY_SWITCH if gran == "daily" else WEEKLY_SWITCH
                    yield f"DATA/{key}/{ref}/{gran}/{group}", rows, boundary
    for group, rows in margins.items():
        if not isinstance(rows, list):
            _fail(f"MARGES_GZ/{group} is not a list")
        yield f"MARGES_GZ/{group}", rows, WEEKLY_SWITCH


def _validate_dates(name: str, rows: list[dict]) -> list[date]:
    parsed = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or "date" not in row:
            _fail(f"invalid row shape in {name} at index {index}")
        parsed.append(_as_date(row["date"], f"{name}[{index}].date"))
    if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
        _fail(f"invalid date ordering in {name}")
    return parsed


def _validate_bouclier_contract(meta: dict, *, source_max: date, target_end: date) -> None:
    try:
        c2_bouclier_contract.validate_bouclier_contract(
            meta, source_max=source_max, target_end=target_end
        )
    except ValueError as exc:
        _fail(str(exc))


def _validate_visible_metadata(meta: dict, summary: dict) -> tuple[date, date, date]:
    source_max = _as_date(meta.get("official_source_max_date"), "meta.official_source_max_date")
    shared_source_max = _as_date(
        meta.get("official_shared_source_max_date"), "meta.official_shared_source_max_date"
    )
    target_end = _as_date(meta.get("daily_target_end"), "meta.daily_target_end")
    weekly_end = _as_date(meta.get("weekly_complete_through"), "meta.weekly_complete_through")
    if source_max != shared_source_max:
        _fail(
            "official_source_max_date differs from official_shared_source_max_date: "
            f"{source_max} != {shared_source_max}"
        )
    if target_end > source_max:
        _fail(f"target_end={target_end} source_max={source_max}")
    expected_weekly_end = _last_complete_sunday(target_end)
    if weekly_end != expected_weekly_end:
        _fail(
            f"weekly_complete_through={weekly_end} does not match target_end={target_end} "
            f"(expected {expected_weekly_end})"
        )
    if summary.get("target_end") != target_end.isoformat():
        _fail(
            f"summary target_end={summary.get('target_end')!r} differs from "
            f"meta.daily_target_end={target_end}"
        )
    if summary.get("weekly_end") != weekly_end.isoformat():
        _fail(
            f"summary weekly_end={summary.get('weekly_end')!r} differs from "
            f"meta.weekly_complete_through={weekly_end}"
        )
    release_tag = meta.get("official_shared_release_tag")
    if not release_tag:
        _fail("missing official_shared_release_tag")
    if summary.get("c1_release_tag") != release_tag:
        _fail("summary C1 release differs from candidate metadata")
    if ((meta.get("v2") or {}).get("c1_release_tag")) != release_tag:
        _fail("V2 C1 release differs from candidate metadata")
    return source_max, target_end, weekly_end


def _validate_new_row(name: str, row: dict, *, index: int) -> None:
    ecart = _finite(row.get("ecart"), f"{name}[{index}].ecart")
    if name.startswith("MARGES_GZ/"):
        corse = _finite(row.get("corse"), f"{name}[{index}].corse")
        bdr = _finite(row.get("bdr"), f"{name}[{index}].bdr")
        if abs(ecart - round(corse - bdr, 2)) > 0.011:
            _fail(
                f"{name}[{index}] margin gap incoherent: ecart={ecart}, "
                f"corse-bdr={corse - bdr:.2f}"
            )


def _validate_series_bounds_and_values(
    name: str,
    rows: list[dict],
    dates: list[date],
    *,
    boundary: date,
    old_len: int,
    initial: bool,
    target_end: date,
    weekly_end: date,
) -> None:
    if "/daily/" in name:
        if any(day > target_end for day in dates):
            _fail(f"{name} contains a date after daily_target_end={target_end}")
    else:
        for day in dates:
            if day + timedelta(days=6) > weekly_end:
                _fail(f"{name} contains an incomplete/future week starting {day}")

    if initial:
        indexes = [i for i, day in enumerate(dates) if day >= boundary]
    else:
        indexes = range(old_len, len(rows))
    for index in indexes:
        _validate_new_row(name, rows[index], index=index)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", default="outputs/v2-production-candidate.json")
    p.add_argument("--summary", default="outputs/v2-production-summary.json")
    p.add_argument("--target", default="data.json")
    p.add_argument("--promote", action="store_true")
    args = p.parse_args()

    candidate_path = ROOT / args.candidate
    summary_path = ROOT / args.summary
    target_path = ROOT / args.target
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    baseline = json.loads(target_path.read_text(encoding="utf-8"))

    meta = candidate.get("meta") or {}
    v2 = meta.get("v2") or {}
    baseline_v2 = (baseline.get("meta") or {}).get("v2") or {}
    initial = not bool(baseline_v2.get("active"))
    if (
        not v2.get("active")
        or v2.get("daily_switch_date") != DAILY_SWITCH.isoformat()
        or v2.get("weekly_switch_date") != WEEKLY_SWITCH.isoformat()
    ):
        _fail("invalid V2 activation metadata")
    if summary.get("missing_replacements_total") != 0:
        _fail("missing transition replacement dates")
    if int((summary.get("engine") or {}).get("r2_unavailable", 0)) != 0:
        _fail("R2 unavailable in production-shaped run")
    guards = summary.get("official_event_guards") or {}
    if int(guards.get("event_rows", 0)) <= 0 or not guards.get("reopening_rule"):
        _fail("official event guards absent")
    if guards.get("release_tag") != meta.get("official_shared_release_tag"):
        _fail("event release differs from pinned C1 release")

    source_max, target_end, weekly_end = _validate_visible_metadata(meta, summary)
    _validate_bouclier_contract(meta, source_max=source_max, target_end=target_end)

    old = dict((name, (rows, boundary)) for name, rows, boundary in iter_series(baseline))
    new = dict((name, (rows, boundary)) for name, rows, boundary in iter_series(candidate))
    if set(old) != set(new):
        _fail("public series topology changed")

    protected = 0
    for name, (old_rows, boundary) in old.items():
        new_rows, _ = new[name]
        dates = _validate_dates(name, new_rows)
        if len(new_rows) < len(old_rows):
            _fail(f"{name} shrank")
        if initial:
            old_prefix = [r for r in old_rows if _as_date(r["date"], f"{name}.date") < boundary]
            new_prefix = [r for r in new_rows if _as_date(r["date"], f"{name}.date") < boundary]
            if new_prefix != old_prefix:
                _fail(f"pre-transition history changed in {name}")
            protected += len(old_prefix)
        else:
            if new_rows[: len(old_rows)] != old_rows:
                _fail(f"post-activation historical rewrite in {name}")
            protected += len(old_rows)
        _validate_series_bounds_and_values(
            name,
            new_rows,
            dates,
            boundary=boundary,
            old_len=len(old_rows),
            initial=initial,
            target_end=target_end,
            weekly_end=weekly_end,
        )

    if initial and int(summary.get("rewritten_rows_total", 0)) <= 0:
        _fail("initial transition rewrote no rows")
    if not initial and int(summary.get("rewritten_rows_total", 0)) != 0:
        _fail("recurring V2 build attempted historical rewrites")

    print(
        json.dumps(
            {
                "status": "V2 candidate verified",
                "initial_transition": initial,
                "protected_rows_verified": protected,
                "rewritten_rows": summary.get("rewritten_rows_total"),
                "added_rows": summary.get("added_rows_total"),
                "target_end": target_end.isoformat(),
                "production_modified": bool(args.promote),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.promote:
        target_path.write_text(candidate_path.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()
