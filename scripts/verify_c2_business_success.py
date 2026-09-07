#!/usr/bin/env python3
"""Prove C2 business success from consumed C1 release through GitHub Pages."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request

DEFAULT_DATA_URL = "https://fredericp555.github.io/carburantscorse2/data.json"
DEFAULT_SUMMARY_URL = "https://fredericp555.github.io/carburantscorse2/homepage-summary.json"


class BusinessSuccessError(RuntimeError):
    pass


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _json(blob: bytes, label: str) -> dict:
    try:
        obj = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BusinessSuccessError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise BusinessSuccessError(f"{label} JSON root is not an object")
    return obj


def _iso(raw, label: str) -> str:
    if not raw:
        raise BusinessSuccessError(f"missing {label}")
    try:
        return date.fromisoformat(str(raw)).isoformat()
    except ValueError as exc:
        raise BusinessSuccessError(f"invalid {label}={raw!r}") from exc


def _hex_digest(raw: str, label: str) -> str:
    value = str(raw or "").strip().lower()
    if value.startswith("sha256:"):
        value = value.split(":", 1)[1]
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise BusinessSuccessError(f"invalid {label}={raw!r}")
    return value


def _data_contract(blob: bytes, label: str) -> dict:
    obj = _json(blob, label)
    meta = obj.get("meta") or {}
    daily = _iso(meta.get("daily_target_end"), f"{label}.meta.daily_target_end")
    weekly = _iso(meta.get("weekly_complete_through"), f"{label}.meta.weekly_complete_through")
    if daily != weekly:
        raise BusinessSuccessError(f"{label}: daily cutoff {daily} != weekly cutoff {weekly}")
    tag = str(meta.get("official_shared_release_tag") or "")
    v2_tag = str(((meta.get("v2") or {}).get("c1_release_tag")) or "")
    if not tag or tag != v2_tag:
        raise BusinessSuccessError(f"{label}: inconsistent C1 release tags {tag!r} / {v2_tag!r}")
    snapshot = _hex_digest(meta.get("official_shared_sha256"), f"{label}.meta.official_shared_sha256")
    return {"through": daily, "c1_release_tag": tag, "c1_snapshot_sha256": snapshot}


def _summary_contract(blob: bytes, label: str) -> dict:
    obj = _json(blob, label)
    if obj.get("schema") != "a4c-homepage-summary-v1":
        raise BusinessSuccessError(f"{label}: unexpected schema {obj.get('schema')!r}")
    source = obj.get("source") or {}
    daily = _iso(source.get("daily_data_through"), f"{label}.source.daily_data_through")
    weekly = _iso(source.get("weekly_data_through"), f"{label}.source.weekly_data_through")
    if daily != weekly:
        raise BusinessSuccessError(f"{label}: daily cutoff {daily} != weekly cutoff {weekly}")
    tag = str(source.get("c1_release_tag") or "")
    if not tag:
        raise BusinessSuccessError(f"{label}: missing source.c1_release_tag")
    snapshot = _hex_digest(source.get("c1_snapshot_sha256"), f"{label}.source.c1_snapshot_sha256")
    return {"through": daily, "c1_release_tag": tag, "c1_snapshot_sha256": snapshot}


def evaluate_publication(
    expected_data: bytes,
    expected_summary: bytes,
    pages_data: bytes,
    pages_summary: bytes,
    *,
    expected_commit: str,
    data_url: str,
    summary_url: str,
    c1_release_tag: str,
    c1_bundle_digest: str,
) -> dict:
    expected_d = _data_contract(expected_data, "expected data.json")
    expected_s = _summary_contract(expected_summary, "expected homepage-summary.json")
    pages_d = _data_contract(pages_data, "Pages data.json")
    pages_s = _summary_contract(pages_summary, "Pages homepage-summary.json")

    if expected_d != expected_s:
        raise BusinessSuccessError(
            f"local C2 data/summary provenance differs: data={expected_d}, summary={expected_s}"
        )
    if pages_d != expected_d or pages_s != expected_s:
        raise BusinessSuccessError("Pages C2 business metadata differs from expected production metadata")

    supplied_tag = str(c1_release_tag or "")
    if supplied_tag != expected_d["c1_release_tag"]:
        raise BusinessSuccessError(
            f"referenced C1 release {expected_d['c1_release_tag']} != verified release {supplied_tag}"
        )
    release_digest = _hex_digest(c1_bundle_digest, "C1 release bundle digest")
    if release_digest != expected_d["c1_snapshot_sha256"]:
        raise BusinessSuccessError(
            f"C1 release asset digest {release_digest} != consumed snapshot {expected_d['c1_snapshot_sha256']}"
        )

    expected_data_sha = sha256_bytes(expected_data)
    pages_data_sha = sha256_bytes(pages_data)
    expected_summary_sha = sha256_bytes(expected_summary)
    pages_summary_sha = sha256_bytes(pages_summary)
    if pages_data_sha != expected_data_sha:
        raise BusinessSuccessError(
            f"Pages data.json SHA differs: expected={expected_data_sha}, pages={pages_data_sha}"
        )
    if pages_summary_sha != expected_summary_sha:
        raise BusinessSuccessError(
            f"Pages homepage-summary.json SHA differs: expected={expected_summary_sha}, pages={pages_summary_sha}"
        )

    return {
        "status": "business-success",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "commit": expected_commit,
        "data_url": data_url,
        "summary_url": summary_url,
        "data_through": expected_d["through"],
        "c1_release_tag": expected_d["c1_release_tag"],
        "c1_snapshot_sha256": expected_d["c1_snapshot_sha256"],
        "c1_release_bundle_sha256": release_digest,
        "expected_data_sha256": expected_data_sha,
        "pages_data_sha256": pages_data_sha,
        "expected_summary_sha256": expected_summary_sha,
        "pages_summary_sha256": pages_summary_sha,
    }


def _cache_bust(url: str, attempt: int) -> str:
    parts = urlsplit(url)
    q = parse_qsl(parts.query, keep_blank_values=True)
    q.append(("a4c_verify", f"{int(time.time() * 1000)}-{attempt}"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


def _fetch_one(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
        "User-Agent": "A4C-C2-business-success/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise BusinessSuccessError(f"Pages returned HTTP {status} for {url}")
        return response.read()


def fetch_pair(data_url: str, summary_url: str) -> tuple[bytes, bytes]:
    return _fetch_one(data_url), _fetch_one(summary_url)


def wait_for_publication(
    expected_data: bytes,
    expected_summary: bytes,
    *,
    data_url: str,
    summary_url: str,
    expected_commit: str,
    c1_release_tag: str,
    c1_bundle_digest: str,
    timeout_seconds: float = 300,
    interval_seconds: float = 5,
    fetcher: Callable[[str, str], tuple[bytes, bytes]] = fetch_pair,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    start = monotonic()
    attempts = 0
    last_error: Exception | None = None
    while True:
        attempts += 1
        try:
            data_b, summary_b = fetcher(
                _cache_bust(data_url, attempts), _cache_bust(summary_url, attempts)
            )
            receipt = evaluate_publication(
                expected_data, expected_summary, data_b, summary_b,
                expected_commit=expected_commit,
                data_url=data_url,
                summary_url=summary_url,
                c1_release_tag=c1_release_tag,
                c1_bundle_digest=c1_bundle_digest,
            )
            receipt["attempts"] = attempts
            return receipt
        except Exception as exc:
            last_error = exc
        elapsed = monotonic() - start
        if elapsed >= timeout_seconds:
            raise BusinessSuccessError(
                f"C2 business success not proven after {attempts} attempts / {elapsed:.1f}s: {last_error}"
            ) from last_error
        sleeper(interval_seconds)


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception as exc:
        raise BusinessSuccessError("cannot determine checked-out commit") from exc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--expected-data", default="data.json")
    p.add_argument("--expected-summary", default="homepage-summary.json")
    p.add_argument("--data-url", default=DEFAULT_DATA_URL)
    p.add_argument("--summary-url", default=DEFAULT_SUMMARY_URL)
    p.add_argument("--commit")
    p.add_argument("--c1-release-tag", required=True)
    p.add_argument("--c1-bundle-digest", required=True)
    p.add_argument("--output", default="outputs/c2-business-success.json")
    p.add_argument("--timeout-seconds", type=float, default=300)
    p.add_argument("--interval-seconds", type=float, default=5)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    data_path = Path(args.expected_data)
    summary_path = Path(args.expected_summary)
    if not data_path.is_file() or not summary_path.is_file():
        raise BusinessSuccessError("expected C2 data.json/homepage-summary.json not found")
    receipt = wait_for_publication(
        data_path.read_bytes(), summary_path.read_bytes(),
        data_url=args.data_url,
        summary_url=args.summary_url,
        expected_commit=args.commit or _git_head(),
        c1_release_tag=args.c1_release_tag,
        c1_bundle_digest=args.c1_bundle_digest,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
