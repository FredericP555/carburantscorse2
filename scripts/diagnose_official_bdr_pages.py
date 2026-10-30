#!/usr/bin/env python3
"""Read-only HTTP diagnosis of official Bouches-du-Rhone station pages.

Single source: prix-carburants.gouv.fr. No registry/data modification.
Uses the same URL, User-Agent, Accept header, HTML parser and classifier as C2.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit
import urllib.error
import urllib.request

from scripts.resolve_new_bdr_station_brands import (
    STATION_URL, USER_AGENT, TextTokens, classify_station,
    extract_brand_from_html, load_corrections,
)

TARGETS = ("13013011", "13120001", "13530003", "13740003")
CONTROL = "13920005"  # previously resolved officially; one request only
OFFICIAL_HOSTS = {"www.prix-carburants.gouv.fr", "prix-carburants.gouv.fr"}
DELAYS = (0, 3, 8)  # seconds before each of the three attempts
TIMEOUT_SECONDS = 12
REPORT = Path("outputs/diagnostic-official-bdr-20261030.json")


class OfficialOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.hops = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute_url = urljoin(req.full_url, newurl)
        parsed = urlsplit(absolute_url)
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise RuntimeError("Redirect blocked: destination outside official HTTPS domain")
        self.hops.append({"status": code, "url": absolute_url})
        return super().redirect_request(req, fp, code, msg, headers, absolute_url)


def safe_headers(headers):
    return {
        name: value
        for name in ("Server", "Via", "Retry-After", "Location", "Content-Type",
                     "CF-Ray", "X-Cache")
        if (value := headers.get(name))
    }


def inspect(station_id):
    url = STATION_URL.format(station_id=station_id)
    redirects = OfficialOnlyRedirects()
    opener = urllib.request.build_opener(redirects)
    request = urllib.request.Request(
        url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    result = {
        "at": datetime.now(timezone.utc).isoformat(),
        "station_id": station_id,
        "request_url": url,
        "redirects": redirects.hops,
    }
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            response_url = response.geturl()
            parsed = urlsplit(response_url)
            if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
                raise RuntimeError("Final response outside official HTTPS domain")
            raw = response.read().decode("utf-8", errors="replace")
            brand = extract_brand_from_html(raw)
            result.update({
                "status": response.status,
                "final_url": response_url,
                "headers": safe_headers(response.headers),
                "response_bytes": len(raw.encode("utf-8")),
                "brand_label_in_text": bool(re.search(r"Marque\s*:", raw, flags=re.I)),
                "extracted_brand": brand,
            })
            if not brand:
                # Inspect only structure and short visible text from the official page.
                # A 200 can be an error page or a station page without the brand field.
                from html import unescape
                match = re.search(r"<title[^>]*>(.*?)</title\s*>", raw, flags=re.I | re.S)
                result["page_title"] = unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else None
                parser = TextTokens()
                parser.feed(raw)
                markers = ("station", "marque", "introuvable", "erreur", "carburant", "recherche")
                result["official_page_text_markers"] = [
                    token[:170] for token in parser.tokens
                    if any(marker in token.casefold() for marker in markers)
                ][:20]
                result["official_page_text_tail"] = parser.tokens[-12:]
            if brand:
                by_id, by_brand = load_corrections()
                segment, detail, source = classify_station(station_id, brand, by_id, by_brand)
                result["classification"] = {
                    "segment": segment, "detail": detail, "source": source
                }
            else:
                result["error"] = "Marque not found by C2's official HTML parser"
    except urllib.error.HTTPError as exc:
        result.update({
            "status": exc.code,
            "final_url": exc.geturl(),
            "headers": safe_headers(exc.headers),
            "error": f"HTTPError: HTTP {exc.code} {exc.reason}",
        })
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError, RuntimeError) as exc:
        result.update({"error": f"{type(exc).__name__}: {exc}"})
    return result


def main():
    records = []
    for station_id in (*TARGETS, CONTROL):
        delays = DELAYS if station_id in TARGETS else (0,)
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)
            result = inspect(station_id)
            result["attempt"] = attempt
            result["control"] = station_id == CONTROL
            records.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    summary = {
        "source": "https://www.prix-carburants.gouv.fr/",
        "no_external_station_sources": True,
        "mode": "read-only",
        "user_agent": USER_AGENT,
        "timeout_seconds": TIMEOUT_SECONDS,
        "records": records,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Diagnostic written to {REPORT}; no registry or published data changed.")


if __name__ == "__main__":
    main()
