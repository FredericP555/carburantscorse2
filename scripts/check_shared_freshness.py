#!/usr/bin/env python3
"""Fail loudly when the shared C1 input is stale, globally or by required fuel.

The weekly C2 job depends on independent freshness signals:
1. the GitHub Release itself must be recent (pipeline freshness);
2. the official stock's global max_date must not be stale or move backwards;
3. Gazole, SP95 and E10 must each be fresh in the snapshot actually decoded from the pinned
   C1 release, so one fresh fuel cannot hide another stale fuel.

The per-fuel dates are derived from decoded release rows, then persisted into the candidate
metadata before promotion. This makes subsequent runs able to detect a per-fuel regression.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
import re
from pathlib import Path
from typing import Any

from a4c_common.shared_release import load_shared_observations
from a4c_common.source_freshness import max_date_by_fuel

REQUIRED_FRESHNESS_FUELS = ("Gazole", "SP95", "E10")
DEFAULT_SHARED_META = Path("outputs/ufip/c1_shared_meta.json")


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


def _release_timestamp(candidate_meta: dict[str, Any]) -> tuple[str | None, str | None]:
    raw = candidate_meta.get("official_shared_release_published_at")
    if raw:
        return str(raw), "metadata"
    tag = str(candidate_meta.get("official_shared_release_tag") or "")
    match = re.fullmatch(r"a4c(?:-v2)?-shared-(\d{8}T\d{6}Z)-.+", tag)
    if match:
        parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z"), "release-tag"
    return None, None


def _tag_prefix(tag: str) -> str:
    if tag.startswith("a4c-v2-shared-"):
        return "a4c-v2-shared-"
    if tag.startswith("a4c-shared-"):
        return "a4c-shared-"
    raise RuntimeError(f"Unsupported C1 shared release tag for freshness derivation: {tag!r}")


def derive_actual_per_fuel_dates(
    candidate_meta: dict[str, Any],
    *,
    shared_meta_path: Path = DEFAULT_SHARED_META,
) -> dict[str, str]:
    """Decode the pinned C1 snapshot and derive each fuel's actual latest observation date."""
    tag = str(candidate_meta.get("official_shared_release_tag") or "")
    if not tag:
        raise RuntimeError("Cannot derive per-fuel freshness without a pinned C1 release tag")
    if not shared_meta_path.is_file():
        raise RuntimeError(f"C1 shared metadata file is missing: {shared_meta_path}")
    shared_meta = json.loads(shared_meta_path.read_text(encoding="utf-8"))
    years = sorted({int(y) for y in shared_meta.get("years", [])})
    if not years:
        raise RuntimeError("C1 shared metadata has no source years for per-fuel freshness")
    rows, source = load_shared_observations(
        years,
        tag_prefix=_tag_prefix(tag),
        release_tag=tag,
    )
    if str(source.get("release_tag") or "") != tag:
        raise RuntimeError("Decoded C1 freshness snapshot does not match the pinned release tag")
    return max_date_by_fuel(rows)


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

    release_raw, release_timestamp_source = _release_timestamp(candidate_meta)
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

    current_by_fuel_raw = candidate_meta.get("official_shared_source_max_date_by_fuel")
    previous_by_fuel_raw = baseline_meta.get("official_shared_source_max_date_by_fuel")
    source_dates_by_fuel: dict[str, str | None] = {}
    source_age_days_by_fuel: dict[str, int | None] = {}
    progression_by_fuel: dict[str, str] = {}

    if not isinstance(current_by_fuel_raw, dict):
        failures.append("shared official per-fuel max_date metadata is missing")
        current_by_fuel_raw = {}
    if not isinstance(previous_by_fuel_raw, dict):
        previous_by_fuel_raw = {}
        warnings.append("baseline has no per-fuel max_date metadata yet; regression check starts after this migration")

    for fuel in REQUIRED_FRESHNESS_FUELS:
        raw = current_by_fuel_raw.get(fuel)
        source_dates_by_fuel[fuel] = None if raw is None else str(raw)
        source_age_days_by_fuel[fuel] = None
        progression_by_fuel[fuel] = "unknown"
        if not raw:
            failures.append(f"{fuel} per-fuel max_date is missing from the decoded C1 snapshot")
            continue
        try:
            current_fuel = _parse_date(str(raw))
        except ValueError:
            failures.append(f"invalid {fuel} per-fuel max_date: {raw!r}")
            continue

        age = (now.date() - current_fuel).days
        source_age_days_by_fuel[fuel] = age
        if age < -1:
            failures.append(f"{fuel} per-fuel max_date is unexpectedly in the future ({raw})")
        elif age > max_source_age_days:
            failures.append(
                f"{fuel} official stock is stale (max_date={raw}, age={age} d; limit {max_source_age_days} d)"
            )

        previous_fuel_raw = previous_by_fuel_raw.get(fuel)
        if not previous_fuel_raw:
            progression_by_fuel[fuel] = "baseline-unavailable"
            continue
        try:
            previous_fuel = _parse_date(str(previous_fuel_raw))
        except ValueError:
            progression_by_fuel[fuel] = "baseline-invalid"
            warnings.append(f"baseline {fuel} per-fuel max_date is invalid: {previous_fuel_raw!r}")
            continue
        if current_fuel < previous_fuel:
            progression_by_fuel[fuel] = "regressed"
            failures.append(
                f"{fuel} official stock regressed from {previous_fuel.isoformat()} to {current_fuel.isoformat()}"
            )
        elif current_fuel == previous_fuel:
            progression_by_fuel[fuel] = "unchanged"
            warnings.append(f"{fuel} official stock max_date did not advance ({current_fuel.isoformat()})")
        else:
            progression_by_fuel[fuel] = "advanced"

    return {
        "status": "fail" if failures else "ok",
        "release_tag": candidate_meta.get("official_shared_release_tag"),
        "release_published_at": release_raw,
        "release_timestamp_source": release_timestamp_source,
        "release_age_hours": None if release_age_hours is None else round(release_age_hours, 2),
        "source_max_date": source_raw,
        "source_age_days": source_age_days,
        "previous_source_max_date": previous_raw,
        "source_progression": progression,
        "source_max_date_by_fuel": source_dates_by_fuel,
        "source_age_days_by_fuel": source_age_days_by_fuel,
        "source_progression_by_fuel": progression_by_fuel,
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
    candidate_path = Path(args.candidate)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate_meta = _meta(candidate)
    baseline_meta = _meta(baseline)

    actual_by_fuel = derive_actual_per_fuel_dates(candidate_meta)
    existing_by_fuel = candidate_meta.get("official_shared_source_max_date_by_fuel")
    if isinstance(existing_by_fuel, dict) and existing_by_fuel != actual_by_fuel:
        raise RuntimeError(
            "candidate per-fuel freshness metadata differs from the pinned C1 snapshot: "
            f"candidate={existing_by_fuel!r} decoded={actual_by_fuel!r}"
        )
    candidate_meta["official_shared_source_max_date_by_fuel"] = actual_by_fuel

    now = _parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    report = evaluate_shared_freshness(
        candidate_meta,
        baseline_meta,
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
            for fuel in REQUIRED_FRESHNESS_FUELS:
                handle.write(
                    f"- {fuel} max_date: `{report['source_max_date_by_fuel'].get(fuel)}` "
                    f"({report['source_age_days_by_fuel'].get(fuel)} d old; "
                    f"{report['source_progression_by_fuel'].get(fuel)})\n"
                )
            for warning in report["warnings"]:
                handle.write(f"- warning: {warning}\n")
            for failure in report["failures"]:
                handle.write(f"- failure: {failure}\n")

    if report["failures"]:
        raise SystemExit(1)

    candidate_path.write_text(
        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
