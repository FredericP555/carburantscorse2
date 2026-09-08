#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import quote

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from a4c_common.shared_release import (
    CORSE_BRANDS_ASSET,
    DATA_ASSET,
    META_ASSET,
    ROTTERDAM_DAILY_ASSET,
    ROTTERDAM_OBSERVED_ASSET,
    _asset_url,
    _decode_snapshot,
    _request_bytes,
    _request_json,
)
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories
from scripts.build_v2_production_candidate import (
    LEGACY_BDR, BDR_REGISTRY, C1_META, C1_TAG, CORSE_REGISTRY,
    ROTTERDAM_DAILY, ROTTERDAM_OBSERVED,
    _bdr_category_resolver, _evaluate_v2,
)
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

DAY = date(2026, 8, 24)
HISTORICAL = "a4c-v2-shared-20260824T232328Z-32788829663"
LATEST = "a4c-v2-shared-20260908T011056Z-34175476841"
REPOSITORY = "FredericP555/carburantscorse1"


def published_rows() -> dict:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    out = {}
    for ref, _bdr_fuel in (("sp95", "SP95"), ("e10", "E10")):
        for scope, group in (("all", "all"), ("network", "reseau")):
            rows = data["DATA"]["sp95"][ref]["daily"][group]
            row = next(r for r in rows if str(r["date"]) == DAY.isoformat())
            out[f"{ref}/{scope}"] = deepcopy(row)
    return out


def _verified_asset(release: dict, name: str, expected_sha: str | None) -> bytes:
    payload = _request_bytes(_asset_url(release, name), timeout=240)
    if expected_sha:
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected_sha:
            raise RuntimeError(f"{name} SHA mismatch: expected={expected_sha} actual={actual}")
    return payload


def load_release_for_historical_audit(tag: str) -> tuple[list[dict], dict, dict]:
    """Load one immutable C1 release while preserving the contract that existed at publication.

    Production C2 intentionally rejects old releases that predate the Sep-2026 Rotterdam semantic
    fields. This audit must nevertheless inspect the immutable Aug-24 snapshot. We therefore verify
    the release asset SHAs and decoded manifest, but do not require metadata fields introduced later.
    """
    url = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}"
    release = _request_json(url)
    if str(release.get("tag_name") or "") != tag or release.get("draft"):
        raise RuntimeError(f"Unavailable historical release {tag}")

    metadata = json.loads(_request_bytes(_asset_url(release, META_ASSET)).decode("utf-8"))
    years = sorted(int(y) for y in metadata.get("years", []))
    data_bytes = _verified_asset(release, DATA_ASSET, str(metadata.get("sha256") or "") or None)
    observations = _decode_snapshot(data_bytes, metadata, years)

    rot = metadata.get("rotterdam") or {}
    observed_name = str(rot.get("observed_asset") or ROTTERDAM_OBSERVED_ASSET)
    daily_name = str(rot.get("daily_asset") or ROTTERDAM_DAILY_ASSET)
    observed = _verified_asset(release, observed_name, str(rot.get("observed_sha256") or "") or None)
    daily = _verified_asset(release, daily_name, str(rot.get("daily_sha256") or "") or None)

    brands = metadata.get("corse_station_brands") or {}
    brands_name = str(brands.get("asset") or CORSE_BRANDS_ASSET)
    brands_bytes = _verified_asset(release, brands_name, str(brands.get("sha256") or "") or None)
    brands_payload = json.loads(brands_bytes.decode("utf-8"))
    if not isinstance(brands_payload.get("stations"), dict) or not brands_payload["stations"]:
        raise RuntimeError(f"Invalid Corsica brand registry in {tag}")

    C1_META.parent.mkdir(parents=True, exist_ok=True)
    C1_META.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    C1_TAG.parent.mkdir(parents=True, exist_ok=True)
    C1_TAG.write_text(tag + "\n", encoding="utf-8")
    CORSE_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    CORSE_REGISTRY.write_bytes(brands_bytes)
    ROTTERDAM_OBSERVED.parent.mkdir(parents=True, exist_ok=True)
    ROTTERDAM_OBSERVED.write_bytes(observed)
    ROTTERDAM_DAILY.write_bytes(daily)

    source = {
        "release_tag": tag,
        "release_published_at": release.get("published_at"),
        "shared_source_max_date": metadata.get("max_date"),
        "sha256": metadata.get("sha256"),
        "bouclier": metadata.get("bouclier"),
        "rotterdam": metadata.get("rotterdam"),
    }
    return observations, source, metadata


def recompute(tag: str) -> dict:
    shutil.rmtree(ROOT / "outputs" / "c1", ignore_errors=True)
    shutil.rmtree(ROOT / "outputs" / "ufip", ignore_errors=True)
    (ROOT / "outputs" / "c1").mkdir(parents=True, exist_ok=True)
    (ROOT / "outputs" / "ufip").mkdir(parents=True, exist_ok=True)

    observations, source, meta = load_release_for_historical_audit(tag)
    source_max = date.fromisoformat(str(source["shared_source_max_date"]))
    assert source_max >= DAY, (tag, source_max)

    legacy = load_bdr_categories(LEGACY_BDR)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    state = build_publication_state(
        pd.DataFrame(observations),
        global_end=pd.Timestamp(DAY),
        bdr_category_resolver=resolver,
    )
    bouclier = source.get("bouclier") or meta.get("bouclier")
    guards = EventGuards.from_release(tag, metadata=meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}
    v2_state, engine = _evaluate_v2(
        state,
        bouclier=bouclier,
        event_guards=guards,
        corse_stations=corse_stations,
        start=DAY,
        end=DAY,
    )

    out = {"tag": tag, "source_max": source_max.isoformat(), "snapshot_sha256": source.get("sha256"), "engine": engine, "rows": {}}
    for ref, bdr_fuel in (("sp95", "SP95"), ("e10", "E10")):
        for scope, _group in (("all", "all"), ("network", "reseau")):
            rows = build_gap_series(
                v2_state,
                corsica_fuel="SP95",
                bdr_fuel=bdr_fuel,
                bdr_scope=scope,
                granularity="daily",
            )
            row = next(r for r in rows if str(r["date"]) == DAY.isoformat())
            out["rows"][f"{ref}/{scope}"] = row
    return out


def main() -> None:
    published = published_rows()
    historical = recompute(HISTORICAL)
    latest = recompute(LATEST)
    result = {"published": published, "historical_release": historical, "latest_release": latest, "comparison": {}}
    for key in published:
        p = published[key]
        h = historical["rows"][key]
        l = latest["rows"][key]
        result["comparison"][key] = {
            "published_ecart": p.get("ecart"),
            "historical_ecart": h.get("ecart"),
            "latest_ecart": l.get("ecart"),
            "historical_minus_published_c_l": round(float(h["ecart"]) - float(p["ecart"]), 6),
            "latest_minus_published_c_l": round(float(l["ecart"]) - float(p["ecart"]), 6),
            "historical_row": h,
            "latest_row": l,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
