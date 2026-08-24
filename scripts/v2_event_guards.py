#!/usr/bin/env python3
"""Load official rupture/closure intervals from one pinned C1 release.

Rule for open-ended official events:
- an open rupture stays active until a later official declaration of the same fuel;
- an open closure stays active until a later official declaration of any fuel at the station;
- an explicit official end date always has priority over a later price declaration.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import os
from urllib.parse import quote
import urllib.request

EVENT_ASSET = "official_13_20_events.csv.gz"
EVENT_SCHEMA = "a4c-official-13-20-events-v1"
DEFAULT_PRICE_ASSET = "official_13_20.csv.gz"
DEFAULT_REPOSITORY = "FredericP555/carburantscorse1"


def _headers() -> dict[str, str]:
    headers = {"User-Agent": "A4C-v2-event-guards/1.0", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token: headers["Authorization"] = f"Bearer {token}"
    return headers

def _bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(request, timeout=timeout) as response: return response.read()
def _json(url: str): return json.loads(_bytes(url, 60).decode("utf-8"))
def _asset_url(release: dict, name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name and asset.get("browser_download_url"): return str(asset["browser_download_url"])
    raise RuntimeError(f"Pinned C1 release {release.get('tag_name')} has no asset {name}")
def _parse_day(raw: str | None) -> date | None:
    value=str(raw or "").strip(); return date.fromisoformat(value) if value else None
def _parse_dt(raw) -> datetime | None:
    value=str(raw or "").strip()
    if not value: return None
    try: dt=datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return None
    if dt.tzinfo is not None: dt=dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
def _active(day: date, start: date, end: date | None) -> bool: return start <= day and (end is None or day <= end)
def _read_gzip_csv(payload: bytes) -> list[dict]:
    rows=[]
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
            rows.extend(dict(row) for row in csv.DictReader(text))
    return rows

class EventGuards:
    def __init__(self, rows: list[dict], *, release_tag: str, metadata: dict):
        self.release_tag=release_tag; self.metadata=metadata; self.rows=rows; self.calls=Counter(); self.hit_ruptures=set(); self.hit_closures=set(); self.bound_to_declarations=False; self.reopen_stats=Counter(); self.declaration_source_asset=None
        self.raw_ruptures={}; self.raw_closures={}; self.ruptures={}; self.closures={}; seen=set()
        for row in rows:
            sid=str(row.get("station_id") or "").strip(); kind=str(row.get("event_kind") or "").strip(); fuel=str(row.get("fuel") or "").strip(); event_type=str(row.get("event_type") or "").strip(); started=_parse_dt(row.get("started_at")); ended=_parse_dt(row.get("ended_at"))
            if started is None:
                start_day=_parse_day(row.get("start_date")); started=datetime.combine(start_day,datetime.min.time()) if start_day else None
            if ended is None:
                end_day=_parse_day(row.get("end_date")); ended=datetime.combine(end_day,datetime.max.time()) if end_day else None
            if not sid or kind not in {"rupture","fermeture"} or started is None: continue
            key=(sid,kind,fuel,event_type,started,ended)
            if key in seen: continue
            seen.add(key); interval=(started,ended,event_type)
            if kind=="rupture":
                if fuel: self.raw_ruptures.setdefault((sid,fuel),[]).append(interval)
            else: self.raw_closures.setdefault(sid,[]).append(interval)
        for values in self.raw_ruptures.values(): values.sort(key=lambda item:(item[0],item[1] or datetime.max,item[2]))
        for values in self.raw_closures.values(): values.sort(key=lambda item:(item[0],item[1] or datetime.max,item[2]))

    @classmethod
    def from_release(cls, release_tag: str, *, metadata: dict, repository: str = DEFAULT_REPOSITORY) -> "EventGuards":
        event_meta=metadata.get("official_events")
        if not isinstance(event_meta,dict) or event_meta.get("schema") != EVENT_SCHEMA: raise RuntimeError("Pinned C1 metadata has no valid official-event contract")
        event_asset_name=str(event_meta.get("asset") or EVENT_ASSET); url=f"https://api.github.com/repos/{repository}/releases/tags/{quote(release_tag,safe='')}"; release=_json(url)
        if str(release.get("tag_name") or "") != release_tag: raise RuntimeError("Pinned C1 release lookup returned a different tag")
        event_payload=_bytes(_asset_url(release,event_asset_name),180); expected_event_sha=str(event_meta.get("sha256") or "")
        if not expected_event_sha or hashlib.sha256(event_payload).hexdigest() != expected_event_sha: raise RuntimeError("Official-event asset SHA-256 mismatch")
        rows=_read_gzip_csv(event_payload)
        if len(rows) != int(event_meta.get("rows",-1)): raise RuntimeError("Official-event row count differs from C1 metadata")
        guard=cls(rows,release_tag=release_tag,metadata=event_meta)
        price_asset_name=str(metadata.get("asset") or DEFAULT_PRICE_ASSET); price_payload=_bytes(_asset_url(release,price_asset_name),180); expected_price_sha=str(metadata.get("sha256") or "")
        if not expected_price_sha or hashlib.sha256(price_payload).hexdigest() != expected_price_sha: raise RuntimeError("Pinned official price asset SHA-256 mismatch while binding event guards")
        guard.declaration_source_asset=price_asset_name; guard.bind_observations(_read_gzip_csv(price_payload)); return guard

    def bind_observations(self, observations) -> None:
        by_station_fuel={}; by_station={}
        for row in observations:
            if hasattr(row,"to_dict"): row=row.to_dict()
            sid=str(row.get("station_id") or "").strip(); fuel=str(row.get("fuel") or "").strip(); ts=_parse_dt(row.get("timestamp"))
            if not sid or not fuel or ts is None: continue
            by_station_fuel.setdefault((sid,fuel),[]).append(ts); by_station.setdefault(sid,[]).append(ts)
        for values in by_station_fuel.values(): values.sort()
        for values in by_station.values(): values.sort()
        self.ruptures={}; self.closures={}; self.reopen_stats.clear()
        for key,intervals in self.raw_ruptures.items():
            declarations=by_station_fuel.get(key,[]); effective=[]
            for started,ended,event_type in intervals:
                end_day=ended.date() if ended is not None else None
                if ended is not None: self.reopen_stats["rupture_explicit_end"] += 1
                else:
                    idx=bisect_right(declarations,started)
                    if idx < len(declarations):
                        reopen=declarations[idx]; end_day=reopen.date()-timedelta(days=1); self.reopen_stats["rupture_open_closed_by_declaration"] += 1
                        if reopen.date()==started.date(): self.reopen_stats["rupture_same_day_reopen"] += 1
                    else: self.reopen_stats["rupture_open_remaining"] += 1
                if end_day is not None and end_day < started.date(): self.reopen_stats["rupture_effectively_empty_after_reopen"] += 1; continue
                effective.append((started.date(),end_day,event_type))
            if effective: self.ruptures[key]=effective
        for sid,intervals in self.raw_closures.items():
            declarations=by_station.get(sid,[]); effective=[]
            for started,ended,event_type in intervals:
                end_day=ended.date() if ended is not None else None
                if ended is not None: self.reopen_stats["closure_explicit_end"] += 1
                else:
                    idx=bisect_right(declarations,started)
                    if idx < len(declarations):
                        reopen=declarations[idx]; end_day=reopen.date()-timedelta(days=1); self.reopen_stats["closure_open_closed_by_declaration"] += 1
                        if reopen.date()==started.date(): self.reopen_stats["closure_same_day_reopen"] += 1
                    else: self.reopen_stats["closure_open_remaining"] += 1
                if end_day is not None and end_day < started.date(): self.reopen_stats["closure_effectively_empty_after_reopen"] += 1; continue
                effective.append((started.date(),end_day,event_type))
            if effective: self.closures[sid]=effective
        for values in self.ruptures.values(): values.sort(key=lambda item:(item[0],item[1] or date.max,item[2]))
        for values in self.closures.values(): values.sort(key=lambda item:(item[0],item[1] or date.max,item[2]))
        self.bound_to_declarations=True

    def _require_bound(self):
        if not self.bound_to_declarations: raise RuntimeError("Official event guards must be bound to price declarations before evaluation")
    def rupture_active(self, station_id: str, fuel: str, day: date) -> bool:
        self._require_bound(); self.calls["rupture_checks"] += 1; verdict=any(_active(day,start,end) for start,end,_ in self.ruptures.get((str(station_id),str(fuel)),[]))
        if verdict: self.calls["rupture_true"] += 1; self.hit_ruptures.add((str(station_id),str(fuel),day))
        return verdict
    def independently_inactive(self, station_id: str, day: date) -> bool:
        self._require_bound(); self.calls["closure_checks"] += 1; verdict=any(_active(day,start,end) for start,end,_ in self.closures.get(str(station_id),[]))
        if verdict: self.calls["closure_true"] += 1; self.hit_closures.add((str(station_id),day))
        return verdict
    def audit(self) -> dict:
        kind_counts=Counter(str(row.get("event_kind") or "") for row in self.rows); dept_counts=Counter(str(row.get("department") or "") for row in self.rows); start_dates=sorted(d for d in (_parse_day(row.get("start_date")) for row in self.rows) if d is not None)
        return {"source":"official prix-carburants.gouv.fr rupture/fermeture nodes via pinned C1 release","release_tag":self.release_tag,"schema":self.metadata.get("schema"),"asset":self.metadata.get("asset"),"declaration_source_asset":self.declaration_source_asset,"event_rows":len(self.rows),"rows_by_kind":dict(kind_counts),"rows_by_department":dict(dept_counts),"min_start_date":start_dates[0].isoformat() if start_dates else None,"max_start_date":start_dates[-1].isoformat() if start_dates else None,"reopening_rule":{"rupture_open_end":"first later official price declaration of the same fuel","closure_open_end":"first later official price declaration of any fuel at the station","explicit_end_priority":True,"declaration_day_considered_reopened":True},"reopening_stats":dict(self.reopen_stats),"rupture_interval_keys":len(self.ruptures),"closure_station_keys":len(self.closures),"engine_checks":dict(self.calls),"unique_active_rupture_station_fuel_days":len(self.hit_ruptures),"unique_active_closure_station_days":len(self.hit_closures)}
