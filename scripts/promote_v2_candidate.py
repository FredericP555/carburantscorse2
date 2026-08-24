#!/usr/bin/env python3
"""Verify and optionally promote the controlled A4C V2 production candidate.

Without --promote this is a strict read-only preflight. With --promote it writes the
already-verified candidate bytes to data.json. Initial activation permits rewrites only
from 2026-07-23 daily / 2026-07-27 weekly+margin. Every later V2 run is append-only.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_SWITCH = date(2026, 7, 23)
WEEKLY_SWITCH = date(2026, 7, 27)


def iter_series(obj: dict):
    for key, refs in obj["DATA"].items():
        for ref, grans in refs.items():
            for gran, groups in grans.items():
                for group, rows in groups.items():
                    boundary = DAILY_SWITCH if gran == "daily" else WEEKLY_SWITCH
                    yield f"DATA/{key}/{ref}/{gran}/{group}", rows, boundary
    for group, rows in obj["MARGES_GZ"].items():
        yield f"MARGES_GZ/{group}", rows, WEEKLY_SWITCH


def _validate_dates(name: str, rows: list[dict]) -> None:
    dates=[str(r["date"]) for r in rows]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise SystemExit(f"Refusing V2 candidate: invalid date ordering in {name}")


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--candidate",default="outputs/v2-production-candidate.json"); p.add_argument("--summary",default="outputs/v2-production-summary.json"); p.add_argument("--target",default="data.json"); p.add_argument("--promote",action="store_true"); args=p.parse_args()
    candidate_path=ROOT/args.candidate; summary_path=ROOT/args.summary; target_path=ROOT/args.target
    candidate=json.loads(candidate_path.read_text(encoding="utf-8")); summary=json.loads(summary_path.read_text(encoding="utf-8")); baseline=json.loads(target_path.read_text(encoding="utf-8"))
    meta=candidate.get("meta") or {}; v2=meta.get("v2") or {}; baseline_v2=(baseline.get("meta") or {}).get("v2") or {}; initial=not bool(baseline_v2.get("active"))
    if not v2.get("active") or v2.get("daily_switch_date") != DAILY_SWITCH.isoformat() or v2.get("weekly_switch_date") != WEEKLY_SWITCH.isoformat(): raise SystemExit("Refusing V2 candidate: invalid V2 activation metadata")
    if summary.get("missing_replacements_total") != 0: raise SystemExit("Refusing V2 candidate: missing transition replacement dates")
    if int((summary.get("engine") or {}).get("r2_unavailable",0)) != 0: raise SystemExit("Refusing V2 candidate: R2 unavailable in production-shaped run")
    guards=summary.get("official_event_guards") or {}
    if int(guards.get("event_rows",0)) <= 0 or not guards.get("reopening_rule"): raise SystemExit("Refusing V2 candidate: official event guards absent")
    if guards.get("release_tag") != meta.get("official_shared_release_tag"): raise SystemExit("Refusing V2 candidate: event release differs from pinned C1 release")
    source_max=meta.get("official_source_max_date"); target_end=meta.get("daily_target_end")
    if not source_max or not target_end or target_end > source_max: raise SystemExit(f"Refusing V2 candidate: target_end={target_end} source_max={source_max}")

    old=dict((name,(rows,boundary)) for name,rows,boundary in iter_series(baseline)); new=dict((name,(rows,boundary)) for name,rows,boundary in iter_series(candidate))
    if set(old) != set(new): raise SystemExit("Refusing V2 candidate: public series topology changed")
    protected=0
    for name,(old_rows,boundary) in old.items():
        new_rows,_=new[name]; _validate_dates(name,new_rows)
        if len(new_rows) < len(old_rows): raise SystemExit(f"Refusing V2 candidate: {name} shrank")
        if initial:
            old_prefix=[r for r in old_rows if date.fromisoformat(str(r["date"])) < boundary]
            new_prefix=[r for r in new_rows if date.fromisoformat(str(r["date"])) < boundary]
            if new_prefix != old_prefix: raise SystemExit(f"Refusing V2 candidate: pre-transition history changed in {name}")
            protected += len(old_prefix)
        else:
            if new_rows[:len(old_rows)] != old_rows: raise SystemExit(f"Refusing V2 candidate: post-activation historical rewrite in {name}")
            protected += len(old_rows)
    if initial and int(summary.get("rewritten_rows_total",0)) <= 0: raise SystemExit("Refusing V2 candidate: initial transition rewrote no rows")
    if not initial and int(summary.get("rewritten_rows_total",0)) != 0: raise SystemExit("Refusing V2 candidate: recurring V2 build attempted historical rewrites")

    print(json.dumps({"status":"V2 candidate verified","initial_transition":initial,"protected_rows_verified":protected,"rewritten_rows":summary.get("rewritten_rows_total"),"added_rows":summary.get("added_rows_total"),"target_end":target_end,"production_modified":bool(args.promote)},ensure_ascii=False,indent=2))
    if args.promote:
        target_path.write_text(candidate_path.read_text(encoding="utf-8"),encoding="utf-8")

if __name__ == "__main__": main()
