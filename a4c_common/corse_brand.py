from __future__ import annotations

import unicodedata
from typing import Mapping

TOTAL = "TOTAL"
NON_TOTAL_CONFIRMED = "NON_TOTAL_CONFIRMED"
UNKNOWN = "UNKNOWN"


def _alnum(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(ch for ch in text if ch.isascii() and ch.isalnum())


def classify_registry_entry(entry: Mapping | None) -> str:
    if not isinstance(entry, Mapping):
        return UNKNOWN
    brand = str(entry.get("enseigne") or "").strip()
    segment = _alnum(entry.get("segment"))
    source = _alnum(entry.get("brand_source"))
    if not brand or segment == "inconnu" or source in {"nonresolu", "unresolved"}:
        return UNKNOWN
    normalized = _alnum(brand)
    if normalized == "total" or normalized.startswith("totalenergies") or normalized.startswith("totalaccess"):
        return TOTAL
    return NON_TOTAL_CONFIRMED
