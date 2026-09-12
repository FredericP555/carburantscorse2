#!/usr/bin/env python3
"""Bounded, auditable BDR category backfill for monthly reconstruction only.

C2 production remains strictly temporal and append-only. The monthly reconstruction may need to
classify a station-day a few days before the first *verified* category attached to the same stable
station_id. This module only fills that category gap; it never changes price, source timestamp,
or station-day eligibility.

Policy:
- keep the normal C2 category whenever it already exists;
- only look forward for the same station_id;
- require a verified, resolved category no more than MAX_BACKFILL_DAYS later;
- never cross contradictory brand/category evidence in the interval;
- record every applied station-day for the internal monthly audit.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from scripts.resolve_new_bdr_station_brands import (
    classification_for_day,
    segment_to_legacy_category,
)

MAX_BACKFILL_DAYS = 7


def _day(value: Any) -> date | None:
    # pandas.Timestamp is datetime-like. Convert it to a plain datetime.date before passing it to
    # the production temporal resolver, whose boundaries are datetime.date objects.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _brand(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _periods(entry: dict | None) -> list[dict]:
    if not isinstance(entry, dict):
        return []
    periods: list[dict] = []
    for item in entry.get("brand_history") or []:
        if not isinstance(item, dict):
            continue
        start = _day(item.get("valid_from"))
        if start is None:
            continue
        periods.append({
            "start": start,
            "end": _day(item.get("valid_to")),
            "enseigne": str(item.get("enseigne") or ""),
            "segment": str(item.get("segment") or ""),
            "verified_at": str(item.get("verified_at") or ""),
            "source": "history",
        })
    start = _day(entry.get("brand_valid_from") or entry.get("first_seen"))
    if start is not None:
        periods.append({
            "start": start,
            "end": None,
            "enseigne": str(entry.get("enseigne") or ""),
            "segment": str(entry.get("segment") or ""),
            "verified_at": str(entry.get("verified_at") or ""),
            "source": "current",
        })
    periods.sort(key=lambda x: (x["start"], x["end"] or date.max, x["source"]))
    return periods


def _overlaps(period: dict, start: date, end: date) -> bool:
    p_start = period["start"]
    p_end = period["end"] or date.max
    return p_start <= end and p_end >= start


class MonthlyBdrCategoryResolver:
    """Callable resolver wrapping C2's temporal classification with a bounded monthly backfill."""

    def __init__(
        self,
        legacy_categories: dict[str, str],
        registry: dict,
        *,
        window_start: date,
        window_end: date,
        max_backfill_days: int = MAX_BACKFILL_DAYS,
    ) -> None:
        self.legacy = {str(k): str(v) for k, v in legacy_categories.items()}
        self.registry = registry
        self.window_start = window_start
        self.window_end = window_end
        self.max_backfill_days = int(max_backfill_days)
        self._applied: dict[tuple[str, date], dict] = {}
        self._rejected_conflicts: dict[tuple[str, date], dict] = {}

    def __call__(self, station_id: str, value: Any) -> str | None:
        sid = str(station_id)
        day = _day(value)
        if day is None:
            raise ValueError(f"Invalid category date: {value!r}")

        # C2 production classification always wins when it is already known.
        base = classification_for_day(sid, day, self.legacy, self.registry)
        if base is not None:
            return base
        if day < self.window_start or day > self.window_end:
            return None

        entry = (self.registry.get("stations") or {}).get(sid)
        periods = _periods(entry)
        candidates: list[tuple[int, dict, str]] = []
        for period in periods:
            category = segment_to_legacy_category(period["segment"])
            if category not in {"gms", "network"} or not period["verified_at"]:
                continue
            delta = (period["start"] - day).days
            if 0 < delta <= self.max_backfill_days:
                candidates.append((delta, period, category))
        if not candidates:
            return None

        _delta, candidate, category = min(candidates, key=lambda x: (x[0], x[1]["start"]))
        interval_end = candidate["start"]
        candidate_brand = _brand(candidate["enseigne"])
        conflicts: list[dict] = []
        for period in periods:
            if period is candidate or not _overlaps(period, day, interval_end):
                continue
            p_category = segment_to_legacy_category(period["segment"])
            p_brand = _brand(period["enseigne"])
            category_conflict = p_category is not None and p_category != category
            brand_conflict = bool(p_brand and candidate_brand and p_brand != candidate_brand)
            if category_conflict or brand_conflict:
                conflicts.append({
                    "valid_from": period["start"].isoformat(),
                    "valid_to": None if period["end"] is None else period["end"].isoformat(),
                    "enseigne": period["enseigne"],
                    "category": p_category,
                })
        if conflicts:
            self._rejected_conflicts[(sid, day)] = {
                "station_id": sid,
                "day": day.isoformat(),
                "candidate_valid_from": candidate["start"].isoformat(),
                "candidate_enseigne": candidate["enseigne"],
                "candidate_category": category,
                "conflicts": conflicts,
            }
            return None

        self._applied[(sid, day)] = {
            "station_id": sid,
            "day": day,
            "category": category,
            "enseigne": candidate["enseigne"],
            "classification_valid_from": candidate["start"],
            "verified_at": candidate["verified_at"],
        }
        return category

    def audit(self) -> dict:
        applied = sorted(self._applied.values(), key=lambda x: (x["station_id"], x["day"]))
        ranges: list[dict] = []
        for row in applied:
            if (
                ranges
                and ranges[-1]["station_id"] == row["station_id"]
                and ranges[-1]["category"] == row["category"]
                and ranges[-1]["enseigne"] == row["enseigne"]
                and ranges[-1]["classification_valid_from"] == row["classification_valid_from"].isoformat()
                and (row["day"] - date.fromisoformat(ranges[-1]["through"])).days == 1
            ):
                ranges[-1]["through"] = row["day"].isoformat()
                ranges[-1]["station_days"] += 1
            else:
                ranges.append({
                    "station_id": row["station_id"],
                    "from": row["day"].isoformat(),
                    "through": row["day"].isoformat(),
                    "station_days": 1,
                    "category": row["category"],
                    "enseigne": row["enseigne"],
                    "classification_valid_from": row["classification_valid_from"].isoformat(),
                    "verified_at": row["verified_at"],
                })
        rejected = [self._rejected_conflicts[k] for k in sorted(self._rejected_conflicts)]
        return {
            "policy": {
                "scope": "monthly_reconstruction_only",
                "same_station_id_required": True,
                "max_backfill_days": self.max_backfill_days,
                "verified_future_category_required": True,
                "contradictory_brand_or_category_blocks": True,
                "price_or_eligibility_modified": False,
                "window_start": self.window_start.isoformat(),
                "window_end": self.window_end.isoformat(),
            },
            "applied_station_days": len(applied),
            "applied_network_station_days": sum(1 for x in applied if x["category"] == "network"),
            "applied_gms_station_days": sum(1 for x in applied if x["category"] == "gms"),
            "applied_ranges": ranges,
            "rejected_conflicts": rejected,
        }


def monthly_bdr_category_resolver(
    legacy_categories: dict[str, str],
    registry: dict,
    *,
    window_start: date,
    window_end: date,
    max_backfill_days: int = MAX_BACKFILL_DAYS,
) -> MonthlyBdrCategoryResolver:
    return MonthlyBdrCategoryResolver(
        legacy_categories,
        registry,
        window_start=window_start,
        window_end=window_end,
        max_backfill_days=max_backfill_days,
    )
