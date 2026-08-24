#!/usr/bin/env python3
"""Load official rupture/closure intervals from one pinned C1 prep release.

Prep-only helper for the V2 live dry-run. It does not mutate production data.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import gzip
import hashlib
import io
import json
import os
from urllib.parse import quote
import urllib.request

EVENT_ASSET = "official_13_20_events.csv.gz"
EVENT_SCHEMA = "a4c-official-13-20-events-v1"
DEFAULT_REPOSITORY = "FredericP555/carburantscorse1"


def _headers() -> dict[str, str]:
    headers = {
        "User-Agent": "A4C-v2-event-guards/1.0",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _json(url: str):
    return json.loads(_bytes(url, 60).decode("utf-8"))


def _asset_url(release: dict, name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name and asset.get("browser_download_url"):
            return str(asset["browser_download_url"])
    raise RuntimeError(f"Pinned C1 release {release.get('tag_name')} has no asset {name}")


def _parse_day(raw: str | None) -> date | None:
    value = str(raw or "").strip()
    return date.fromisoformat(value) if value else None


def _active(day: date, start: date, end: date | None) -> bool:
    return start <= day and (end is None or day <= end)


class EventGuards:
    def __init__(self, rows: list[dict], *, release_tag: str, metadata: dict):
        self.release_tag = release_tag
        self.metadata = metadata
        self.ruptures: dict[tuple[str, str], list[tuple[date, date | None, str]]] = {}
        self.closures: dict[str, list[tuple[date, date | None, str]]] = {}
        self.rows = rows
        self.calls = Counter()
        self.hit_ruptures: set[tuple[str, str, date]] = set()
        self.hit_closures: set[tuple[str, date]] = set()

        seen = set()
        for row in rows:
            sid = str(row.get("station_id") or "").strip()
            kind = str(row.get("event_kind") or "").strip()
            fuel = str(row.get("fuel") or "").strip()
            event_type = str(row.get("event_type") or "").strip()
            start = _parse_day(row.get("start_date"))
            end = _parse_day(row.get("end_date"))
            if not sid or kind not in {"rupture", "fermeture"} or start is None:
                continue
            key = (sid, kind, fuel, event_type, start, end)
            if key in seen:
                continue
            seen.add(key)
            interval = (start, end, event_type)
            if kind == "rupture":
                if not fuel:
                    continue
                self.ruptures.setdefault((sid, fuel), []).append(interval)
            else:
                self.closures.setdefault(sid, []).append(interval)

        for values in self.ruptures.values():
            values.sort(key=lambda item: (item[0], item[1] or date.max, item[2]))
        for values in self.closures.values():
            values.sort(key=lambda item: (item[0], item[1] or date.max, item[2]))

    @classmethod
    def from_release(
        cls,
        release_tag: str,
        *,
        metadata: dict,
        repository: str = DEFAULT_REPOSITORY,
    ) -> "EventGuards":
        event_meta = metadata.get("official_events")
        if not isinstance(event_meta, dict) or event_meta.get("schema") != EVENT_SCHEMA:
            raise RuntimeError("Pinned C1 metadata has no valid official-event contract")
        asset_name = str(event_meta.get("asset") or EVENT_ASSET)
        url = f"https://api.github.com/repos/{repository}/releases/tags/{quote(release_tag, safe='')}"
        release = _json(url)
        if str(release.get("tag_name") or "") != release_tag:
            raise RuntimeError("Pinned C1 release lookup returned a different tag")
        payload = _bytes(_asset_url(release, asset_name), 180)
        expected_sha = str(event_meta.get("sha256") or "")
        actual_sha = hashlib.sha256(payload).hexdigest()
        if not expected_sha or actual_sha != expected_sha:
            raise RuntimeError("Official-event asset SHA-256 mismatch")

        rows: list[dict] = []
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                for row in reader:
                    rows.append(dict(row))
        if len(rows) != int(event_meta.get("rows", -1)):
            raise RuntimeError("Official-event row count differs from C1 metadata")
        return cls(rows, release_tag=release_tag, metadata=event_meta)

    def rupture_active(self, station_id: str, fuel: str, day: date) -> bool:
        self.calls["rupture_checks"] += 1
        verdict = any(_active(day, start, end) for start, end, _event_type in self.ruptures.get((str(station_id), str(fuel)), []))
        if verdict:
            self.calls["rupture_true"] += 1
            self.hit_ruptures.add((str(station_id), str(fuel), day))
        return verdict

    def independently_inactive(self, station_id: str, day: date) -> bool:
        self.calls["closure_checks"] += 1
        verdict = any(_active(day, start, end) for start, end, _event_type in self.closures.get(str(station_id), []))
        if verdict:
            self.calls["closure_true"] += 1
            self.hit_closures.add((str(station_id), day))
        return verdict

    def audit(self) -> dict:
        kind_counts = Counter(str(row.get("event_kind") or "") for row in self.rows)
        dept_counts = Counter(str(row.get("department") or "") for row in self.rows)
        start_dates = sorted(
            d for d in (_parse_day(row.get("start_date")) for row in self.rows) if d is not None
        )
        return {
            "source": "official prix-carburants.gouv.fr rupture/fermeture nodes via pinned C1 prep release",
            "release_tag": self.release_tag,
            "schema": self.metadata.get("schema"),
            "asset": self.metadata.get("asset"),
            "event_rows": len(self.rows),
            "rows_by_kind": dict(kind_counts),
            "rows_by_department": dict(dept_counts),
            "min_start_date": start_dates[0].isoformat() if start_dates else None,
            "max_start_date": start_dates[-1].isoformat() if start_dates else None,
            "rupture_interval_keys": len(self.ruptures),
            "closure_station_keys": len(self.closures),
            "engine_checks": dict(self.calls),
            "unique_active_rupture_station_fuel_days": len(self.hit_ruptures),
            "unique_active_closure_station_days": len(self.hit_closures),
            "sample_active_ruptures": [
                {"station_id": sid, "fuel": fuel, "day": day.isoformat()}
                for sid, fuel, day in sorted(self.hit_ruptures, key=lambda x: (x[2], x[0], x[1]))[:20]
            ],
            "sample_active_closures": [
                {"station_id": sid, "day": day.isoformat()}
                for sid, day in sorted(self.hit_closures, key=lambda x: (x[1], x[0]))[:20]
            ],
        }
