#!/usr/bin/env python3
"""Incremental brand resolver for new Bouches-du-Rhône station IDs.

The published 2026 station_id -> gms/network table remains frozen and authoritative for IDs
already known when the dashboard was reconstructed. Only IDs absent from that legacy table
(and absent from the incremental registry) trigger a lookup on the official
prix-carburants.gouv.fr station page.

New-ID A4C rule:
- GMS and low-cost major formats -> gms_lowcost;
- TotalEnergies Access and Esso Express -> gms_lowcost / lowcost_major;
- explicitly recognized classic major/network formats -> traditionnel;
- missing or unrecognized brand -> inconnu, left out of the network-only comparison until resolved.

Resolved and unresolved IDs are retained forever in the incremental registry, so disappeared
stations remain classifiable historically. Unresolved IDs are retried on later updates.
"""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
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
USER_AGENT = "A4C-carburantscorse2-station-brands/1.0"
WORKERS = 4

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
    # Important: low-cost formats are tested before their parent major name.
    if any(_norm(candidate) in normalized for candidate in LOW_COST_MAJORS):
        return "gms_lowcost", "lowcost_major"
    if any(_norm(candidate) in normalized for candidate in GMS):
        return "gms_lowcost", "gms"
    if any(_norm(candidate) in normalized for candidate in MAJORS):
        return "traditionnel", "major_tradi"
    # Fail closed: a fetched but unknown brand must not silently enter the traditional
    # network comparison. It stays unknown until an explicit brand/ID correction exists.
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
            "policy": {
                "legacy": "IDs already present in bdr_categories_published_2026-06-06.csv keep their published category",
                "new_ids": "official brand -> explicit A4C segment/detail; unrecognized brands remain inconnu; Esso Express and TotalEnergies Access are gms_lowcost",
            },
            "stations": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "a4c-bdr-station-brands-v1" or not isinstance(payload.get("stations"), dict):
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


def ids_to_resolve(
    observed_ids: Iterable[str],
    legacy_categories: dict[str, str],
    registry: dict,
) -> list[str]:
    stations = registry.get("stations") or {}
    result: list[str] = []
    for station_id in sorted({str(x) for x in observed_ids if str(x)}):
        if station_id in legacy_categories:
            continue
        entry = stations.get(station_id)
        if not entry or entry.get("segment") == "inconnu" or not entry.get("enseigne"):
            result.append(station_id)
    return result


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


def resolve_from_observations(
    observations: Iterable[dict],
    legacy_categories: dict[str, str],
    *,
    registry_path: Path = DEFAULT_REGISTRY,
    corrections_path: Path = DEFAULT_CORRECTIONS,
    fetcher: Callable[[str], tuple[str | None, str | None]] = fetch_brand,
) -> dict:
    registry = load_registry(registry_path)
    by_id, by_brand = load_corrections(corrections_path)
    observed_ids = observed_bdr_ids(observations)
    pending = ids_to_resolve(observed_ids, legacy_categories, registry)
    stations = {str(k): dict(v) for k, v in (registry.get("stations") or {}).items()}
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

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
            entry = {
                "enseigne": brand,
                "segment": segment,
                "detail": detail,
                "classification_source": source,
                "brand_source": "officiel",
                "first_seen": old.get("first_seen") or today,
                "verified_at": now,
            }
        else:
            errors[station_id] = error or "official brand unavailable"
            entry = {
                "enseigne": old.get("enseigne") or "",
                "segment": "inconnu",
                "detail": "inconnu",
                "classification_source": old.get("classification_source") or "auto",
                "brand_source": "non_resolu",
                "first_seen": old.get("first_seen") or today,
                "verified_at": old.get("verified_at") or "",
            }
        if stations.get(station_id) != entry:
            stations[station_id] = entry
            changed = True

    if changed:
        registry = dict(registry)
        registry["generated_at"] = now
        registry["stations"] = dict(sorted(stations.items()))
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    resolved = resolved_categories({**registry, "stations": stations})
    return {
        "changed": changed,
        "observed_bdr_id_count": len(observed_ids),
        "legacy_known_count": sum(1 for sid in observed_ids if sid in legacy_categories),
        "brand_fetch_count": len(pending),
        "resolved_this_run": len(pending) - len(errors),
        "unresolved_this_run": len(errors),
        "unresolved_ids": sorted(errors),
        "incremental_category_count": len(resolved),
        "categories": resolved,
    }
