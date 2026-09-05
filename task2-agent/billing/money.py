"""Money formatting.

The sandbox works in minor units and warns never to send floats. Amounts stay integers
everywhere in this codebase; this module exists only to render them for humans.
"""
from __future__ import annotations


def fmt(amount_minor, currency: str = "USD") -> str:
    """9900 -> '$99.00'. Never used for arithmetic."""
    if amount_minor is None:
        return "n/a"
    amount_minor = int(amount_minor)
    sign = "-" if amount_minor < 0 else ""
    whole, cents = divmod(abs(amount_minor), 100)
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    return "{}{}{:,}.{:02d}".format(sign, symbol, whole, cents)


def parse_amount_to_minor(text: str):
    """Best-effort '$99.00' / '99' -> 9900. Returns None when it cannot be trusted.

    Only ever used to read a number a *human approver* typed, never to widen a policy
    decision: the result is still clamped by policy.cap_refund_amount.
    """
    if text is None:
        return None
    cleaned = str(text).strip().replace(",", "").replace("$", "")
    if not cleaned:
        return None
    try:
        return int(round(float(cleaned) * 100))
    except ValueError:
        return None
