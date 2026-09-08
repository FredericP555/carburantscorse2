from __future__ import annotations

from datetime import date
from typing import Iterable


def max_date_by_fuel(rows: Iterable[dict]) -> dict[str, str]:
    """Return each fuel's actual latest date from decoded shared-snapshot rows."""
    latest: dict[str, date] = {}
    for row in rows:
        fuel = str(row.get("fuel") or "").strip()
        raw_day = row.get("date")
        if not fuel or raw_day is None:
            continue
        day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day))
        if fuel not in latest or day > latest[fuel]:
            latest[fuel] = day
    return {fuel: latest[fuel].isoformat() for fuel in sorted(latest)}
