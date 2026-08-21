from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MILLI_EUR = Decimal("0.001")


def to_milli_eur(value) -> int | None:
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not dec.is_finite():
        return None
    quantized = dec.quantize(MILLI_EUR, rounding=ROUND_HALF_UP)
    return int(quantized * 1000)


def finite_number(value) -> bool:
    return to_milli_eur(value) is not None


def at_cap(price, cap, *, below_milli: int = 2, above_milli: int = 1) -> bool:
    p = to_milli_eur(price)
    c = to_milli_eur(cap)
    if p is None or c is None:
        return False
    return c - below_milli <= p <= c + above_milli
