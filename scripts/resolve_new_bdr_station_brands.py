#!/usr/bin/env python3
"""Temporal brand resolver for Bouches-du-Rhône station IDs.

The legacy station_id -> category table remains authoritative for already-published history.
From 8 Sep 2026 onward, official station-brand checks may establish a new category for the same
stable ID. Changes are dated and never rewrite earlier published days.
"""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config" / "bdr_station_brands.json"
DEFAULT_CORRECTIONS = ROOT / "config" / "bdr_station_brand_corrections.csv"
STATION_URL = "https://www.prix-carburants.gouv.fr/station/{station_id}"
USER_AGENT = "A4C-carburantscorse2-station-brands/1.1"
WORKERS = 4
TEMPORAL_CATEGORY_START = date(2026, 9, 8)
LEGACY_FROZEN_THROUGH = TEMPORAL_CATEGORY_START - timedelta(days=1)
BRAND_REVERIFY_DAYS = 90
BRAND_REVERIFY_LIMIT = 20

GMS = [
    "leclerc", "e.leclerc", "intermarche", "carrefour", "super u", "hyper u",
    "u express", "systeme u", "auchan", "casino", "geant", "cora", "netto",
    "colruyt", "match", "leader price", "monoprix", "simply", "atac", "bi1",
]
LOW_COST_MAJORS = ["total access", "totalenergies access", "esso express"]
MAJORS = [
    "total", "totalenergies", "elan", "esso", "shell", "bp", "agip", "eni", "mobil",
]
SEGMENTS = {"gms_lowcost", "traditionnel", "inconnu"}
DETAILS = {"gms", "lowcost_major", "major_tradi", "marque_tradi", "inconnu"}


class TextTokens(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.tokens.append(value)


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).casefold().strip()
    for src, dst in (
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("â", "a"), ("ä", "a"),
        ("î", "i"), ("ï", "i"), ("ô", "o"), ("ö", "o"),
        ("û", "u"), ("ù", "u"), ("ü", "u"), ("ç", "c"), ("’", "'"),
    ):
        text = text.replace(src, dst)
    return " ".join(text.split())


def _date_value(value) -> date | None:
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


def extract_brand_from_html(raw: str) -> str | None:
    parser = TextTokens()
    parser.feed(raw)
    tokens = [html.unescape(token).strip() for token in parser.tokens if token.strip()]
    for idx, token in enumerate(tokens):
        compact = re.sub(r"\s+", " ", token).strip()
        match = re.match(r"^Marque\s*:\s*(.*)$", compact, flags=re.I)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline:
            return inline
        for nxt in tokens[idx + 1 : idx + 5]:
            if nxt.strip():
                return nxt.strip()
    return None


def classify_brand(brand: str | None) -> tuple[str, str]:
    normalized = _norm(brand)
    if not normalized:
        return "inconnu", "inconnu"
    if any(_norm(candidate) in normalized for candidate in LOW_COST_MAJORS):
        return "gms_lowcost", "lowcost_major"
    if any(_norm(candidate) in normalized for candidate in GMS):
        return "gms_lowcost", "gms"
    if any(_norm(candidate) in normalized for candidate in MAJORS):
        return "traditionnel", "major_tradi"
    return "inconnu", "inconnu"


def segment_to_legacy_category(segment: str) -> str | None:
    if segment == "gms_lowcost":
        return "gms"
    if segment == "traditionnel":
        return "network"
    return None


def fetch_brand(station_id: str, *, timeout: int = 15) -> tuple[str | None, str | None]:
    request = urllib.request.Request(
        STATION_URL.format(station_id=station_id),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    brand = extract_brand_from_html(raw)
    return (brand, None) if brand else (None, "Marque not found in official station page")


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict:
    if not path.exists():
        return {
            "schema": "a4c-bdr-station-brands-v1",
            "policy": {},
            "stations": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") not in {"a4c-bdr-station-brands-v1", "a4c-bdr-station-brands-v2"} or not isinstance(payload.get("stations"), dict):
        raise RuntimeError(f"Invalid BDR station-brand registry: {path}")
    return payload


def load_corrections(path: Path = DEFAULT_CORRECTIONS) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_brand: dict[str, dict] = {}
    if not path.exists():
        return by_id, by_brand
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"cle", "segment", "detail", "justification"}
        if not reader.fieldnames or not required.issubset({x.strip() for x in reader.fieldnames}):
            raise RuntimeError(f"Invalid correction file header: {path}")
        for row in reader:
            key = (row.get("cle") or "").strip()
            if not key:
                continue
            segment = (row.get("segment") or "").strip()
            detail = (row.get("detail") or "").strip()
            justification = (row.get("justification") or "").strip()
            if segment not in SEGMENTS or detail not in DETAILS or not justification:
                raise RuntimeError(f"Invalid correction for {key!r}")
            value = {"segment": segment, "detail": detail, "justification": justification}
            if key.isdigit():
                by_id[key] = value
            else:
                by_brand[_norm(key)] = value
    return by_id, by_brand


def classify_station(
    station_id: str,
    brand: str | None,
    by_id: dict[str, dict],
    by_brand: dict[str, dict],
) -> tuple[str, str, str]:
    segment, detail = classify_brand(brand)
    source = "auto"
    if _norm(brand) in by_brand:
        corr = by_brand[_norm(brand)]
        segment, detail, source = corr["segment"], corr["detail"], "correction_marque"
    if station_id in by_id:
        corr = by_id[station_id]
        segment, detail, source = corr["segment"], corr["detail"], "correction_id"
    return segment, detail, source


def resolved_categories(registry: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for station_id, entry in (registry.get("stations") or {}).items():
        category = segment_to_legacy_category(str(entry.get("segment") or ""))
        if category:
            result[str(station_id)] = category
    return result


def _entry_for_day(entry: dict | None, day: date) -> dict | None:
    if not isinstance(entry, dict):
        return None
    for period in entry.get("brand_history") or []:
        if not isinstance(period, dict):
            continue
        start = _date_value(period.get("valid_from"))
        end = _date_value(period.get("valid_to"))
        if start is not None and start <= day and (end is None or day <= end):
            return period
    start = _date_value(entry.get("brand_valid_from") or entry.get("first_seen"))
    if start is None or day >= start:
        return entry
    return None


def classification_for_day(
    station_id: str,
    day: date,
    legacy_categories: dict[str, str],
    registry: dict,
) -> str | None:
    """Return gms/network for a date without rewriting the legacy published period."""
    station_id = str(station_id)
    if day <= LEGACY_FROZEN_THROUGH and station_id in legacy_categories:
        return legacy_categories[station_id]
    selected = _entry_for_day((registry.get("stations") or {}).get(station_id), day)
    if selected is not None:
        category = segment_to_legacy_category(str(selected.get("segment") or ""))
        if category:
            return category
    return legacy_categories.get(station_id)


def category_resolver(legacy_categories: dict[str, str], registry: dict):
    return lambda station_id, day: classification_for_day(
        str(station_id), pd_day(day), legacy_categories, registry
    )


def pd_day(value) -> date:
    parsed = _date_value(value)
    if parsed is None:
        raise ValueError(f"Invalid category date: {value!r}")
    return parsed


def _verified_day(entry: dict | None) -> date | None:
    return _date_value((entry or {}).get("verified_at"))


def ids_to_fetch(
    observed_ids: Iterable[str],
    legacy_categories: dict[str, str],
    registry: dict,
    *,
    today: date | None = None,
    reverify_days: int = BRAND_REVERIFY_DAYS,
    limit: int = BRAND_REVERIFY_LIMIT,
) -> list[str]:
    """Target new/unresolved IDs and a bounded oldest-first sample of known IDs."""
    today = today or date.today()
    stations = registry.get("stations") or {}
    ids = sorted({str(x) for x in observed_ids if str(x)})
    mandatory: list[str] = []
    stale: list[tuple[date, str]] = []
    for station_id in ids:
        entry = stations.get(station_id)
        if station_id not in legacy_categories and (
            not entry or entry.get("segment") == "inconnu" or not entry.get("enseigne")
        ):
            mandatory.append(station_id)
            continue
        if entry is not None and (entry.get("segment") == "inconnu" or not entry.get("enseigne")):
            mandatory.append(station_id)
            continue
        verified = _verified_day(entry)
        if verified is None or (today - verified).days >= reverify_days:
            stale.append((verified or date.min, station_id))
    stale.sort(key=lambda item: (item[0], item[1]))
    bounded = [sid for _verified, sid in stale[: max(0, int(limit))]]
    return sorted(dict.fromkeys(mandatory + bounded))


def ids_to_resolve(
    observed_ids: Iterable[str],
    legacy_categories: dict[str, str],
    registry: dict,
) -> list[str]:
    """Backward-compatible name; production now includes bounded known-ID reverification."""
    return ids_to_fetch(observed_ids, legacy_categories, registry)


def observed_bdr_ids(observations: Iterable[dict]) -> set[str]:
    ids: set[str] = set()
    for row in observations:
        if str(row.get("department") or "") != "13":
            continue
        if bool(row.get("is_motorway")) or str(row.get("pop") or "") == "A":
            continue
        station_id = str(row.get("station_id") or "").strip()
        if station_id:
            ids.add(station_id)
    return ids


def _history_record(entry: dict, valid_to: date) -> dict | None:
    if not entry:
        return None
    valid_from = str(entry.get("brand_valid_from") or entry.get("first_seen") or "").strip()
    if not valid_from:
        return None
    return {
        "enseigne": entry.get("enseigne") or "",
        "segment": entry.get("segment") or "inconnu",
        "detail": entry.get("detail") or "inconnu",
        "classification_source": entry.get("classification_source") or "auto",
        "brand_source": entry.get("brand_source") or "officiel",
        "valid_from": valid_from,
        "valid_to": valid_to.isoformat(),
        "verified_at": entry.get("verified_at") or "",
    }


def resolve_from_observations(
    observations: Iterable[dict],
    legacy_categories: dict[str, str],
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    corrections_path: Path = DEFAULT_CORRECTIONS,
    fetcher: Callable[[str], tuple[str | None, str | None]] = fetch_brand,
    today: date | None = None,
    now: datetime | None = None,
    reverify_days: int = BRAND_REVERIFY_DAYS,
    reverify_limit: int = BRAND_REVERIFY_LIMIT,
) -> dict:
    registry = load_registry(registry_path)
    by_id, by_brand = load_corrections(corrections_path)
    observed_ids = observed_bdr_ids(observations)
    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    pending = ids_to_fetch(
        observed_ids,
        legacy_categories,
        registry,
        today=today,
        reverify_days=reverify_days,
        limit=reverify_limit,
    )
    stations = {str(k): dict(v) for k, v in (registry.get("stations") or {}).items()}

    def fetch_one(station_id: str):
        return station_id, fetcher(station_id)

    fetched: dict[str, tuple[str | None, str | None]] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(pending))) as executor:
            fetched = dict(executor.map(fetch_one, pending))

    changed = False
    errors: dict[str, str] = {}
    for station_id in pending:
        old = stations.get(station_id, {})
        brand, error = fetched.get(station_id, (None, "not fetched"))
        if brand:
            segment, detail, source = classify_station(station_id, brand, by_id, by_brand)
            history = [dict(item) for item in (old.get("brand_history") or []) if isinstance(item, dict)]
            old_identity = (
                str(old.get("enseigne") or ""), str(old.get("segment") or ""),
                str(old.get("detail") or ""), str(old.get("classification_source") or ""),
            )
            new_identity = (brand, segment, detail, source)
            if old and old_identity != new_identity:
                previous = _history_record(old, today - timedelta(days=1))
                if previous:
                    history.append(previous)
                valid_from = today.isoformat()
            else:
                valid_from = str(old.get("brand_valid_from") or old.get("first_seen") or today.isoformat())
            entry = {
                "enseigne": brand,
                "segment": segment,
                "detail": detail,
                "classification_source": source,
                "brand_source": "officiel",
                "first_seen": old.get("first_seen") or today.isoformat(),
                "last_seen": today.isoformat(),
                "verified_at": now.isoformat(),
                "brand_valid_from": valid_from,
                "brand_history": history,
            }
        elif old.get("enseigne") and old.get("segment") != "inconnu":
            errors[station_id] = error or "official brand unavailable during reverification"
            entry = dict(old)
            entry["last_seen"] = today.isoformat()
        else:
            errors[station_id] = error or "official brand unavailable"
            if station_id in legacy_categories:
                # Keep legacy fallback; a transient failure must not turn a historically known
                # station into an unknown recent station.
                continue
            entry = {
                "enseigne": old.get("enseigne") or "",
                "segment": "inconnu",
                "detail": "inconnu",
                "classification_source": old.get("classification_source") or "auto",
                "brand_source": "non_resolu",
                "first_seen": old.get("first_seen") or today.isoformat(),
                "last_seen": today.isoformat(),
                "verified_at": old.get("verified_at") or "",
                "brand_valid_from": old.get("brand_valid_from") or today.isoformat(),
                "brand_history": list(old.get("brand_history") or []),
            }
        if stations.get(station_id) != entry:
            stations[station_id] = entry
            changed = True

    result_registry = dict(registry)
    result_registry["schema"] = "a4c-bdr-station-brands-v2"
    result_registry["policy"] = {
        "legacy_frozen_through": LEGACY_FROZEN_THROUGH.isoformat(),
        "temporal_categories_from": TEMPORAL_CATEGORY_START.isoformat(),
        "legacy": "published category remains authoritative through the frozen boundary; later verified brand/category changes apply only from their verification date",
        "new_ids": "official brand -> explicit A4C segment/detail; unrecognized brands remain inconnu; Esso Express and TotalEnergies Access are gms_lowcost",
        "brand_reverify_days": reverify_days,
        "brand_reverify_limit_per_run": reverify_limit,
    }
    result_registry["stations"] = dict(sorted(stations.items()))
    if changed or result_registry != registry:
        result_registry["generated_at"] = now.isoformat()
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(result_registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed = True

    resolved = resolved_categories(result_registry)
    return {
        "changed": changed,
        "observed_bdr_id_count": len(observed_ids),
        "legacy_known_count": sum(1 for sid in observed_ids if sid in legacy_categories),
        "brand_fetch_count": len(pending),
        "resolved_this_run": sum(1 for sid in pending if fetched.get(sid, (None, None))[0]),
        "unresolved_this_run": len(errors),
        "unresolved_ids": sorted(errors),
        "incremental_category_count": len(resolved),
        "categories": resolved,
    }
