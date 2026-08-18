#!/usr/bin/env python3
"""Shared ingestion of the French official fuel-price annual XML stock.

This module deliberately stops before any dashboard-specific reliability rule.
It is intended to be reusable by both A4C observatories:

* carburantscorse1 (Corse vs 12 mainland regions, 45-day state validity), and
* carburantscorse2 (Corse vs Bouches-du-Rhône, territory/fuel reliability rules).

The common layer does only things that are methodologically shared and reversible:
- download one official annual ZIP per year;
- parse station metadata and price declarations;
- keep requested fuels/territories without modifying prices;
- retain whether the station is an autoroute station instead of silently dropping it;
- flag the recovered 1.10–3.00 €/L reliability band without correcting values;
- optionally deduplicate to the last declaration per station/fuel/calendar day.

The default territorial scope remains departments 13 and 20 for carburantscorse2, but callers
may request any postal department prefix, or ``departments=None`` to parse all departments.
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence
import xml.etree.ElementTree as ET

PRICE_MIN = 1.10
PRICE_MAX = 3.00
DEFAULT_FUELS = ("Gazole", "SP95", "E10")
DEFAULT_DEPARTMENTS = ("13", "20")
DEFAULT_CACHE_DIR = Path(".cache/official-fuel")


def annual_url(year: int, *, today: date | None = None) -> str:
    """Return the official annual ZIP endpoint."""
    today = today or date.today()
    if year == today.year:
        return "https://donnees.roulez-eco.fr/opendata/annee"
    return f"https://donnees.roulez-eco.fr/opendata/annee/{year}"


def _validate_zip(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not xml_name:
            raise RuntimeError("Official ZIP contains no XML file")
        return xml_name


def download_annual_zip(
    year: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    force: bool = False,
    user_agent: str = "A4C-observatoires/2.0",
    timeout: int = 240,
) -> Path:
    """Download one official annual ZIP and cache it inside the workflow workspace."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"PrixCarburants_annuel_{year}.zip"
    if path.exists() and not force:
        raw = path.read_bytes()
        try:
            _validate_zip(raw)
            print(f"Using cached official ZIP {path} ({len(raw):,} bytes)", file=sys.stderr)
            return path
        except (RuntimeError, zipfile.BadZipFile):
            path.unlink(missing_ok=True)

    url = annual_url(year)
    print(f"Downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    _validate_zip(raw)

    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    print(f"Saved official ZIP {path} ({len(raw):,} bytes)", file=sys.stderr)
    return path


def department_from_cp(cp: str) -> str | None:
    """Return the two-digit postal department prefix used by the observatories."""
    cp = (cp or "").strip()
    if len(cp) != 5 or not cp.isdigit():
        return None
    if cp.startswith("20"):
        return "20"
    return cp[:2]


def _child_text(elem: ET.Element, tag: str) -> str:
    for child in list(elem):
        if child.tag.rsplit("}", 1)[-1] == tag:
            return (child.text or "").strip()
    return ""


def is_price_in_reference_band(value: float | None) -> bool:
    return value is not None and PRICE_MIN <= value <= PRICE_MAX


def _parse_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def iter_observations_from_zip(
    zip_path: Path,
    *,
    source_year: int | None = None,
    departments: Sequence[str] | None = DEFAULT_DEPARTMENTS,
    fuels: Sequence[str] = DEFAULT_FUELS,
) -> Iterator[dict]:
    """Yield normalized observations without applying dashboard-specific exclusions.

    ``departments=None`` disables the geographic filter. Passing an explicit sequence retains
    the historical selective behaviour; by default only departments 13 and 20 are parsed.
    """
    department_set = None if departments is None else set(departments)
    fuel_set = set(fuels)
    with zipfile.ZipFile(zip_path) as zf:
        xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if not xml_name:
            raise RuntimeError(f"No XML found in {zip_path}")
        inferred_digits = "".join(ch for ch in Path(xml_name).name if ch.isdigit())
        inferred_year = int(inferred_digits[:4]) if len(inferred_digits) >= 4 else None
        year = source_year or inferred_year
        with zf.open(xml_name) as fh:
            for _event, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag.rsplit("}", 1)[-1] != "pdv":
                    continue
                attrs = elem.attrib
                cp = (attrs.get("cp") or "").strip()
                department = department_from_cp(cp)
                if department is None or (
                    department_set is not None and department not in department_set
                ):
                    elem.clear()
                    continue

                station_id = attrs.get("id", "")
                pop = attrs.get("pop", "")
                address = _child_text(elem, "adresse")
                city = _child_text(elem, "ville")
                latitude = attrs.get("latitude", "")
                longitude = attrs.get("longitude", "")

                for child in list(elem):
                    if child.tag.rsplit("}", 1)[-1] != "prix":
                        continue
                    fuel = child.attrib.get("nom", "")
                    if fuel not in fuel_set:
                        continue
                    ts = _parse_timestamp(child.attrib.get("maj"))
                    price = _parse_float(child.attrib.get("valeur"))
                    if ts is None:
                        continue
                    yield {
                        "source_year": year,
                        "station_id": station_id,
                        "department": department,
                        "cp": cp,
                        "city": city,
                        "address": address,
                        "pop": pop,
                        "is_motorway": pop == "A",
                        "latitude": latitude,
                        "longitude": longitude,
                        "fuel_id": child.attrib.get("id", ""),
                        "fuel": fuel,
                        "timestamp": ts,
                        "date": ts.date(),
                        "price": price,
                        "price_in_reference_band": is_price_in_reference_band(price),
                    }
                elem.clear()


def deduplicate_daily(observations: Iterable[dict]) -> list[dict]:
    """Keep the last declaration per station/fuel/day without dropping aberrant values."""
    latest: dict[tuple[str, str, date], dict] = {}
    for row in observations:
        key = (str(row["station_id"]), str(row["fuel"]), row["date"])
        previous = latest.get(key)
        if previous is None or row["timestamp"] >= previous["timestamp"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["station_id"], r["fuel"], r["date"], r["timestamp"]))


NORMALIZED_FIELDS = [
    "source_year", "station_id", "department", "cp", "city", "address", "pop",
    "is_motorway", "latitude", "longitude", "fuel_id", "fuel", "timestamp", "date",
    "price", "price_in_reference_band",
]


def write_normalized_csv(rows: Iterable[dict], path: Path) -> int:
    """Write normalized rows as UTF-8 CSV; return the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            if isinstance(out.get("timestamp"), datetime):
                out["timestamp"] = out["timestamp"].isoformat()
            if isinstance(out.get("date"), date):
                out["date"] = out["date"].isoformat()
            writer.writerow({key: out.get(key, "") for key in NORMALIZED_FIELDS})
            count += 1
    return count