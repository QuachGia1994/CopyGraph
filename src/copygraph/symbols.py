from __future__ import annotations

import re


_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")


def canonicalize_symbol(value: object) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        raise ValueError("symbol is required")
    clean = re.sub(r"[^A-Z0-9]", "", raw)
    if "XAUUSD" in clean or "GOLD" in clean:
        return "XAUUSD"
    if any(alias in clean for alias in ("USTEC", "US100", "NAS100")):
        return "NAS100"
    if any(alias in clean for alias in ("US30", "DJ30", "DJI30")):
        return "US30"
    for base in _CURRENCIES:
        for quote in _CURRENCIES:
            if base == quote:
                continue
            pair = base + quote
            if pair in clean:
                return pair
    return clean
