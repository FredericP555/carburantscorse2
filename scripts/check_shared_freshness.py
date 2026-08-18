#!/usr/bin/env python3
"""Fail loudly when the shared c1 input is stale while distinguishing two failure modes.

The weekly c2 job depends on two independent freshness signals:
1. the GitHub Release itself must be recent (pipeline freshness);
2. the official stock's max_date must not be stale or move backwards (data freshness).

An unchanged max_date is allowed while it is still recent: this is reported explicitly as
"unchanged" rather than being confused with an old/missing c1 Release.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


def _meta(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("meta")
    return value if isinstance(value, dict) else payload


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def evaluate_shared_freshness(
    candidate_meta: dict[str, Any],
    baseline_meta: dict[str, Any],
    *,
    now: datetime,
    max_release_age_hours: float,
    max_source_age_days: int,
) -> dict[str, Any]:
    """Return a deterministic freshness report; callers decide whether to exit non-zero."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    failures: list[str] = []
    warnings: list[str] = []

    if candidate_meta.get("official_ingestion_source") != "c1-github-release":
        failures.append("candidate is not using the required c1 GitHub Release source")

    release_raw = candidate_meta.get("official_shared_release_published_at")
    source_raw = candidate_meta.get("official_shared_source_max_date") or candidate_meta.get("official_source_max_date")

    release_age_hours: float | None = None
    source_age_days: int | None = None
    progression = "unknown"

    if not release_raw:
        failures.append("shared Release publication timestamp is missing")
    else:
        try:
            release_at = _parse_datetime(str(release_raw))
            release_age_hours = (now - release_at).total_seconds() / 3600.0
            if release_age_hours < -1:
                failures.append(f"shared Release timestamp is unexpectedly in the future ({release_raw})")
            elif release_age_hours > max_release_age_hours:
                failures.append(
                    f"shared Release is stale ({release_age_hours:.1f} h old; limit {max_release_age_hours:g} h)"
                )
        except ValueError:
            failures.append(f"invalid shared Release publication timestamp: {release_raw!r}")

    current_source: date | None = None
    if not source_raw:
        failures.append("shared official source max_date is missing")
    else:
        try:
            current_source = _parse_date(str(source_raw))
            source_age_days = (now.date() - current_source).days
            if source_age_days < -1:
                failures.append(f"official source max_date is unexpectedly in the future ({source_raw})")
            elif source_age_days > max_source_age_days:
                failures.append(
                    f"official stock is stale (max_date={source_raw}, age={source_age_days} d; "
                    f"limit {max_source_age_days} d)"
                )
        except ValueError:
            failures.append(f"invalid shared official source max_date: {source_raw!r}")

    previous_raw = baseline_meta.get("official_shared_source_max_date") or baseline_meta.get("official_source_max_date")
    if current_source is not None and previous_raw:
        try:
            previous_source = _parse_date(str(previous_raw))
            if current_source < previous_source:
                progression = "regressed"
                failures.append(
                    f"official stock regressed from {previous_source.isoformat()} to {current_source.isoformat()}"
                )
            elif current_source == previous_source:
                progression = "unchanged"
                warnings.append(
                    f"fresh c1 Release but official stock max_date did not advance ({current_source.isoformat()})"
                )
            else:
                progression = "advanced"
        except ValueError:
            warnings.append(f"baseline official source max_date is invalid: {previous_raw!r}")

    return {
        "status": "fail" if failures else "ok",
        "release_tag": candidate_meta.get("official_shared_release_tag"),
        "release_published_at": release_raw,
        "release_age_hours": None if release_age_hours is None else round(release_age_hours, 2),
        "source_max_date": source_raw,
        "source_age_days": source_age_days,
        "previous_source_max_date": previous_raw,
        "source_progression": progression,
        "failures": failures,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="outputs/candidate-data.json")
    parser.add_argument("--baseline", default="data.json")
    parser.add_argument("--max-release-age-hours", type=float, default=12.0)
    parser.add_argument("--max-source-age-days", type=int, default=4)
    parser.add_argument("--now", help="UTC/offset ISO timestamp, intended for deterministic tests")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    now = _parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    report = evaluate_shared_freshness(
        _meta(candidate),
        _meta(baseline),
        now=now,
        max_release_age_hours=args.max_release_age_hours,
        max_source_age_days=args.max_source_age_days,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("\n### Shared c1 freshness\n\n")
            handle.write(f"- status: **{report['status']}**\n")
            handle.write(f"- release: `{report['release_tag']}` ({report['release_age_hours']} h old)\n")
            handle.write(
                f"- official max_date: `{report['source_max_date']}` "
                f"({report['source_age_days']} d old; {report['source_progression']})\n"
            )
            for warning in report["warnings"]:
                handle.write(f"- warning: {warning}\n")
            for failure in report["failures"]:
                handle.write(f"- failure: {failure}\n")

    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
