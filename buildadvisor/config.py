"""
BuildAdvisor - business-rule configuration (SRS Section 9).

The seed dataset (component catalogue + games) has been removed - components and
games now live only in the SQLite database. The remaining business rules (budget
tiers, minimum budget, resolution multipliers, retailer names) are NOT data; they
are supplied here from environment variables so nothing is hardcoded.

Set them in your .env file (see .env.example). Formats:

    BUILDADVISOR_MIN_BUDGET=42000
    BUILDADVISOR_TIERS=entry:0-55000,mid:55000-110000,high:110000-10000000
    BUILDADVISOR_RESOLUTIONS=1080p:1.0,1440p:1.5,4K:2.6
    BUILDADVISOR_RETAILERS=Amazon,MDComputers,PrimeABGB,Vedant

If a variable is not set, the corresponding value is empty and the logic layer
surfaces a clear "not configured" message instead of crashing.
"""

import os


def _int(name, default=0):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _parse_tiers(raw):
    """'entry:0-55000,mid:55000-110000' -> [('entry',0,55000), ...]"""
    tiers = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk or "-" not in chunk:
            continue
        name, span = chunk.split(":", 1)
        low, high = span.split("-", 1)
        try:
            tiers.append((name.strip(), int(low), int(high)))
        except ValueError:
            continue
    return tiers


def _parse_resolutions(raw):
    """'1080p:1.0,1440p:1.5' -> {'1080p':1.0, '1440p':1.5}"""
    out = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, mult = chunk.split(":", 1)
        try:
            out[name.strip()] = float(mult)
        except ValueError:
            continue
    return out


def _parse_list(raw):
    return [x.strip() for x in raw.split(",") if x.strip()]


# --- Loaded configuration -------------------------------------------------
MIN_BUDGET = _int("BUILDADVISOR_MIN_BUDGET", 0)
TIERS = _parse_tiers(os.environ.get("BUILDADVISOR_TIERS", ""))
RESOLUTIONS = _parse_resolutions(os.environ.get("BUILDADVISOR_RESOLUTIONS", ""))
RETAILERS = _parse_list(os.environ.get("BUILDADVISOR_RETAILERS", ""))


def is_configured() -> bool:
    """True when the essential business rules are present."""
    return bool(MIN_BUDGET and TIERS and RESOLUTIONS and RETAILERS)


def missing() -> list:
    """Names of any business-rule variables that are not configured."""
    gaps = []
    if not MIN_BUDGET:
        gaps.append("BUILDADVISOR_MIN_BUDGET")
    if not TIERS:
        gaps.append("BUILDADVISOR_TIERS")
    if not RESOLUTIONS:
        gaps.append("BUILDADVISOR_RESOLUTIONS")
    if not RETAILERS:
        gaps.append("BUILDADVISOR_RETAILERS")
    return gaps
