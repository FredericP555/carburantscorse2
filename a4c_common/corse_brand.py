from __future__ import annotations

from datetime import date, datetime
import unicodedata
from typing import Mapping

TOTAL = "TOTAL"
NON_TOTAL_CONFIRMED = "NON_TOTAL_CONFIRMED"
UNKNOWN = "UNKNOWN"


def _alnum(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(ch for ch in text if ch.isascii() and ch.isalnum())


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def registry_entry_for_date(entry: Mapping | None, on_date=None) -> Mapping | None:
    if not isinstance(entry, Mapping):
        return None
    target = _day(on_date)
    if target is None:
        return entry
    for period in entry.get("brand_history") or []:
        if not isinstance(period, Mapping):
            continue
        start = _day(period.get("valid_from"))
        end = _day(period.get("valid_to"))
        if start is not None and start <= target and (end is None or target <= end):
            return period
    current_start = _day(entry.get("brand_valid_from"))
    if current_start is not None and target < current_start:
        return None
    return entry


def classify_registry_entry(entry: Mapping | None, *, on_date=None) -> str:
    selected = registry_entry_for_date(entry, on_date)
    if not isinstance(selected, Mapping):
        return UNKNOWN
    brand = str(selected.get("enseigne") or "").strip()
    segment = _alnum(selected.get("segment"))
    source = _alnum(selected.get("brand_source"))
    if not brand or segment == "inconnu" or source in {"nonresolu", "unresolved"}:
        return UNKNOWN
    normalized = _alnum(brand)
    if normalized == "total" or normalized.startswith("totalenergies") or normalized.startswith("totalaccess"):
        return TOTAL
    return NON_TOTAL_CONFIRMED
