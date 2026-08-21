#!/usr/bin/env python3
"""Read the validated shared package published upstream by carburantscorse1.

C1 publishes immutable GitHub Release assets. C2 validates the manifest and SHA-256,
pins one release tag for the whole weekly cycle, and reuses the exact same snapshot,
Rotterdam series and Corsica station-brand registry from that release.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
from datetime import date, datetime
from typing import Iterable
from urllib.parse import quote, urlparse

DEFAULT_REPOSITORY = "FredericP555/carburantscorse1"
DEFAULT_TAG_PREFIX = "a4c-shared-"
DATA_ASSET = "official_13_20.csv.gz"
META_ASSET = "official_13_20.meta.json"
ROTTERDAM_OBSERVED_ASSET = "rotterdam_gazole_observed.csv"
ROTTERDAM_DAILY_ASSET = "rotterdam_gazole_daily.csv"
CORSE_BRANDS_ASSET = "corse_station_brands.json"
SCHEMA = "a4c-official-13-20-v1"
CORSE_BRANDS_SCHEMA = "a4c-corsica-station-brands-v2"
REQUIRED_DEPARTMENTS = {"13", "20"}
REQUIRED_FUELS = {"Gazole", "SP95", "E10"}


def _request_headers(url: str) -> dict[str, str]:
    headers = {
        "User-Agent": "A4C-carburantscorse2/2.0",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and urlparse(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_bytes(url: str, *, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=_request_headers(url))
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


def _release_and_metadata(
    *,
    repository: str = DEFAULT_REPOSITORY,
    tag_prefix: str = DEFAULT_TAG_PREFIX,
    release_tag: str | None = None,
) -> tuple[dict, dict]:
    if release_tag:
        url = f"https://api.github.com/repos/{repository}/releases/tags/{quote(release_tag, safe='')}"
        release = _request_json(url)
        if not isinstance(release, dict) or release.get("draft"):
            raise RuntimeError(f"Shared C1 release tag is unavailable: {release_tag}")
        if not str(release.get("tag_name", "")).startswith(tag_prefix):
            raise RuntimeError(f"Pinned C1 release has unexpected tag: {release.get('tag_name')!r}")
    else:
        releases_url = f"https://api.github.com/repos/{repository}/releases?per_page=30"
        releases = _request_json(releases_url)
        if not isinstance(releases, list):
            raise RuntimeError("GitHub releases API returned an unexpected payload")
        release = _select_shared_release(releases, tag_prefix=tag_prefix)

    metadata = json.loads(_request_bytes(_asset_url(release, META_ASSET)).decode("utf-8"))
    if metadata.get("schema") != SCHEMA:
        raise RuntimeError(f"Unexpected shared snapshot schema: {metadata.get('schema')!r}")
    return release, metadata


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
    release_tag: str | None = None,
) -> tuple[list[dict], dict]:
    """Download and validate one shared release, returning normalized observations."""
    years = sorted({int(year) for year in years})
    release, metadata = _release_and_metadata(
        repository=repository,
        tag_prefix=tag_prefix,
        release_tag=release_tag,
    )
    data_bytes = _request_bytes(_asset_url(release, DATA_ASSET), timeout=240)
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
        "rotterdam": metadata.get("rotterdam"),
        "corse_station_brands": metadata.get("corse_station_brands"),
    }
    return rows, source


def download_shared_rotterdam_assets(
    output_dir: str | Path = "outputs/ufip",
    *,
    repository: str = DEFAULT_REPOSITORY,
    tag_prefix: str = DEFAULT_TAG_PREFIX,
    release_tag: str | None = None,
    registry_output: str | Path = "outputs/c1/corse_station_brands.json",
    tag_output: str | Path = "outputs/c1/shared_release_tag.txt",
) -> dict:
    """Download the complete C1 shared inputs needed by C2; never query UFIP from C2."""
    release, metadata = _release_and_metadata(
        repository=repository,
        tag_prefix=tag_prefix,
        release_tag=release_tag,
    )
    selected_tag = str(release.get("tag_name") or "")
    if not selected_tag:
        raise RuntimeError("Selected C1 release has no tag")

    rotterdam = metadata.get("rotterdam")
    if not isinstance(rotterdam, dict) or not rotterdam.get("single_download"):
        raise RuntimeError("C1 shared release has no canonical Rotterdam metadata")

    observed_name = str(rotterdam.get("observed_asset") or ROTTERDAM_OBSERVED_ASSET)
    daily_name = str(rotterdam.get("daily_asset") or ROTTERDAM_DAILY_ASSET)
    observed_bytes = _request_bytes(_asset_url(release, observed_name), timeout=120)
    daily_bytes = _request_bytes(_asset_url(release, daily_name), timeout=120)

    expected_observed_sha = str(rotterdam.get("observed_sha256") or "")
    expected_daily_sha = str(rotterdam.get("daily_sha256") or "")
    actual_observed_sha = hashlib.sha256(observed_bytes).hexdigest()
    actual_daily_sha = hashlib.sha256(daily_bytes).hexdigest()
    if not expected_observed_sha or actual_observed_sha != expected_observed_sha:
        raise RuntimeError("Shared Rotterdam observed asset SHA-256 mismatch or missing hash")
    if not expected_daily_sha or actual_daily_sha != expected_daily_sha:
        raise RuntimeError("Shared Rotterdam daily asset SHA-256 mismatch or missing hash")

    brands_meta = metadata.get("corse_station_brands")
    if not isinstance(brands_meta, dict):
        raise RuntimeError("C1 shared release has no canonical Corsica brand-registry metadata")
    brands_name = str(brands_meta.get("asset") or CORSE_BRANDS_ASSET)
    brands_bytes = _request_bytes(_asset_url(release, brands_name), timeout=120)
    expected_brands_sha = str(brands_meta.get("sha256") or "")
    actual_brands_sha = hashlib.sha256(brands_bytes).hexdigest()
    if not expected_brands_sha or actual_brands_sha != expected_brands_sha:
        raise RuntimeError("Shared Corsica brand registry SHA-256 mismatch or missing hash")
    brands_payload = json.loads(brands_bytes.decode("utf-8"))
    if brands_payload.get("schema") != CORSE_BRANDS_SCHEMA:
        raise RuntimeError(f"Unexpected shared Corsica brand registry schema: {brands_payload.get('schema')!r}")
    if not isinstance(brands_payload.get("stations"), dict) or not brands_payload["stations"]:
        raise RuntimeError("Shared Corsica brand registry contains no stations")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    observed_path = out / ROTTERDAM_OBSERVED_ASSET
    daily_path = out / ROTTERDAM_DAILY_ASSET
    meta_path = out / "c1_shared_meta.json"
    observed_path.write_bytes(observed_bytes)
    daily_path.write_bytes(daily_bytes)
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    registry_path = Path(registry_output)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_bytes(brands_bytes)

    tag_path = Path(tag_output)
    tag_path.parent.mkdir(parents=True, exist_ok=True)
    tag_path.write_text(selected_tag + "\n", encoding="utf-8")

    return {
        "repository": repository,
        "release_tag": selected_tag,
        "release_published_at": release.get("published_at"),
        "observed_file": str(observed_path),
        "daily_file": str(daily_path),
        "metadata_file": str(meta_path),
        "registry_file": str(registry_path),
        "tag_file": str(tag_path),
        "corsica_calibration": rotterdam.get("corsica_calibration"),
    }
