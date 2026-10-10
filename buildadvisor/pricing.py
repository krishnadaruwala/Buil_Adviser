"""
BuildAdvisor - live component pricing (SRS 4.4 / 7.5 / 9.4).

Fetches live prices for a component by scraping retailer search pages with
`requests` + BeautifulSoup, as specified in the SRS software interface table.
Results are cached with a TTL to reduce repeated external calls (SRS 5.1), and
on any failure the caller falls back to the last-known list price with a
timestamp (SRS 9.4).

Scraping is DISABLED by default so the app runs offline out of the box. Enable
it with:  ENABLE_SCRAPING=1

Note (SRS §13 limitation): retailer page structures change over time, so the
CSS selectors below are best-effort and may need maintenance.
"""

import os
import re
import time

try:
    import requests
except ImportError:  # keep the app importable even if requests is absent
    requests = None

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:  # BeautifulSoup optional; feature degrades gracefully
    _BS4 = False

ENABLED = os.environ.get("ENABLE_SCRAPING", "").strip() in ("1", "true", "True")
CACHE_TTL = int(os.environ.get("PRICE_CACHE_TTL", "3600"))  # seconds (SRS 5.1)
TIMEOUT = 12

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
}

# Retailer search URLs + a price-node CSS selector (best-effort).
# {q} is replaced with the URL-encoded component name.
RETAILERS = {
    "MDComputers": {
        "url": "https://mdcomputers.in/index.php?route=product/search&search={q}",
        "selector": "span.price-normal, div.price",
    },
    "PrimeABGB": {
        "url": "https://www.primeabgb.com/?s={q}&post_type=product",
        "selector": "span.price bdi, span.woocommerce-Price-amount",
    },
    "Vedant": {
        "url": "https://www.vedantcomputers.com/index.php?route=product/search&search={q}",
        "selector": "span.price-new, div.price",
    },
}

# Simple in-memory TTL cache: {(retailer, name): (timestamp, price)}
_cache = {}


def is_enabled() -> bool:
    return ENABLED and _BS4 and requests is not None


def _parse_price(text: str):
    """Extract the first plausible INR amount from a price string."""
    if not text:
        return None
    cleaned = text.replace(",", "")
    m = re.search(r"₹?\s*([0-9]{3,7})(?:\.\d+)?", cleaned)
    if not m:
        return None
    value = int(m.group(1))
    return value if 300 <= value <= 500000 else None


def _scrape_one(retailer: str, cfg: dict, name: str):
    key = (retailer, name)
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    url = cfg["url"].format(q=requests.utils.quote(name))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for node in soup.select(cfg["selector"]):
            price = _parse_price(node.get_text(" ", strip=True))
            if price:
                _cache[key] = (now, price)
                return price
    except (requests.exceptions.RequestException, Exception):
        return None
    return None


def fetch_quotes(component: dict):
    """
    Return {retailer: price} scraped live. Empty dict if scraping is disabled
    or every retailer fails, letting the caller fall back to last-known prices.
    """
    if not is_enabled():
        return {}
    quotes = {}
    for retailer, cfg in RETAILERS.items():
        price = _scrape_one(retailer, cfg, component["name"])
        if price:
            quotes[retailer] = price
    return quotes
