#!/usr/bin/env python3
"""Read the normalized official-price snapshot published by carburantscorse1.

The producer publishes immutable GitHub Release assets. This consumer validates the manifest
and SHA-256 before turning the gzip CSV back into the same row types as official_prices.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import urllib.request
from datetime import date, datetime
from typing import Iterable

DEFAULT_REPOSITORY = "FredericP555/carburantscorse1"
DEFAULT_TAG_PREFIX = "a4c-shared-"
DATA_ASSET = "official_13_20.csv.gz"
META_ASSET = "official_13_20.meta.json"
SCHEMA = "a4c-official-13-20-v1"
REQUIRED_DEPARTMENTS = {"13", "20"}
REQUIRED_FUELS = {"Gazole", "SP95", "E10"}


def _request_bytes(url: str, *, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "A4C-carburantscorse2/2.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _request_json(url: str, *, timeout: int = 60):
    return json.loads(_request_bytes(url, timeout=timeout).decode("utf-8"))


def _select_shared_release(releases: Iterable[dict], *, tag_prefix: str = DEFAULT_TAG_PREFIX) -> dict:
    candidates = [
        release for release in releases
        if not release.get("draft") and str(release.get("tag_name", "")).startswith(tag_prefix)
    ]
    if not candidates:
        raise RuntimeError(f"No published GitHub Release found with prefix {tag_prefix!r}")
    return max(
        candidates,
        key=lambda release: str(release.get("published_at") or release.get("created_at") or ""),
    )


def _asset_url(release: dict, name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name and asset.get("browser_download_url"):
            return str(asset["browser_download_url"])
    raise RuntimeError(f"Release {release.get('tag_name')} has no asset {name}")


def _as_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _decode_snapshot(data_bytes: bytes, metadata: dict, years: Iterable[int]) -> list[dict]:
    requested_years = {int(year) for year in years}
    if metadata.get("schema") != SCHEMA:
        raise RuntimeError(f"Unexpected shared snapshot schema: {metadata.get('schema')!r}")
    available_years = {int(year) for year in metadata.get("years", [])}
    if not requested_years.issubset(available_years):
        raise RuntimeError(
            f"Shared snapshot years {sorted(available_years)} do not cover {sorted(requested_years)}"
        )
    if not REQUIRED_DEPARTMENTS.issubset({str(x) for x in metadata.get("departments", [])}):
        raise RuntimeError("Shared snapshot does not cover departments 13 and 20")
    if not REQUIRED_FUELS.issubset({str(x) for x in metadata.get("fuels", [])}):
        raise RuntimeError("Shared snapshot does not cover Gazole/SP95/E10")

    digest = hashlib.sha256(data_bytes).hexdigest()
    if digest != metadata.get("sha256"):
        raise RuntimeError(
            f"Shared snapshot SHA-256 mismatch: expected={metadata.get('sha256')} actual={digest}"
        )

    rows: list[dict] = []
    with gzip.GzipFile(fileobj=io.BytesIO(data_bytes), mode="rb") as gz:
        with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
            reader = csv.DictReader(text)
            for raw in reader:
                source_year = int(raw["source_year"])
                if source_year not in requested_years:
                    continue
                timestamp = datetime.fromisoformat(raw["timestamp"])
                day = date.fromisoformat(raw["date"])
                price_raw = (raw.get("price") or "").strip()
                price = float(price_raw) if price_raw else None
                rows.append({
                    "source_year": source_year,
                    "station_id": raw.get("station_id", ""),
                    "department": raw.get("department", ""),
                    "cp": raw.get("cp", ""),
                    "city": raw.get("city", ""),
                    "address": raw.get("address", ""),
                    "pop": raw.get("pop", ""),
                    "is_motorway": _as_bool(raw.get("is_motorway")),
                    "latitude": raw.get("latitude", ""),
                    "longitude": raw.get("longitude", ""),
                    "fuel_id": raw.get("fuel_id", ""),
                    "fuel": raw.get("fuel", ""),
                    "timestamp": timestamp,
                    "date": day,
                    "price": price,
                    "price_in_reference_band": _as_bool(raw.get("price_in_reference_band")),
                })

    if not rows:
        raise RuntimeError("Shared snapshot contains no requested observations")
    return rows


def load_shared_observations(
    years: Iterable[int],
    *,
    repository: str = DEFAULT_REPOSITORY,
    tag_prefix: str = DEFAULT_TAG_PREFIX,
) -> tuple[list[dict], dict]:
    """Download and validate the newest shared release, returning normalized observations."""
    years = sorted({int(year) for year in years})
    releases_url = f"https://api.github.com/repos/{repository}/releases?per_page=30"
    releases = _request_json(releases_url)
    if not isinstance(releases, list):
        raise RuntimeError("GitHub releases API returned an unexpected payload")
    release = _select_shared_release(releases, tag_prefix=tag_prefix)

    meta_url = _asset_url(release, META_ASSET)
    data_url = _asset_url(release, DATA_ASSET)
    metadata = json.loads(_request_bytes(meta_url).decode("utf-8"))
    data_bytes = _request_bytes(data_url, timeout=240)
    rows = _decode_snapshot(data_bytes, metadata, years)

    source = {
        "kind": "c1-github-release",
        "repository": repository,
        "release_tag": release.get("tag_name"),
        "release_published_at": release.get("published_at"),
        "schema": metadata.get("schema"),
        "sha256": metadata.get("sha256"),
        "shared_source_max_date": metadata.get("max_date"),
        "shared_rows": metadata.get("rows"),
        "bouclier": metadata.get("bouclier"),
    }
    return rows, source
