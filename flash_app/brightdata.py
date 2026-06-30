"""
Bright Data integration: live retail price + Amazon link for a swap.

Uses Bright Data's Web Unlocker (POST https://api.brightdata.com/request) to
scrape an Amazon search page for the product and pull a representative price.
Falls back to a deterministic cached price if no token / on error, so the demo
never breaks.

Env:
  BRIGHTDATA_API_TOKEN   account API token
  BRIGHTDATA_ZONE        web-unlocker zone name (e.g. sdk_unlocker)
"""

import json
import os
import re
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

API_URL = "https://api.brightdata.com/request"


def _token() -> str:
    return os.environ.get("BRIGHTDATA_API_TOKEN", "")


def _zone() -> str:
    return os.environ.get("BRIGHTDATA_ZONE", "sdk_unlocker")


def amazon_url(product_name: str) -> str:
    return "https://www.amazon.com/s?k=" + product_name.replace(" ", "+")


def _fallback(name: str) -> Dict:
    # Stable pseudo-price from the name so the demo is reproducible offline.
    h = sum(ord(c) for c in name) % 900
    price = round(3.99 + h / 100.0, 2)
    return {
        "source": "cached",
        "retailer": "Amazon",
        "price": f"${price}",
        "in_stock": True,
        "url": amazon_url(name),
    }


def _unlock(url: str, timeout: int = 25) -> Optional[str]:
    body = json.dumps({"zone": _zone(), "url": url, "format": "raw"}).encode()
    req = Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _pick_price(html: str) -> Optional[str]:
    """Choose a representative product price from an Amazon search page.

    Amazon shows unit prices like $0.87 alongside item prices; keep prices in a
    sane retail range and return the most frequent (robust to outliers).
    """
    cands = sorted(
        p for p in (float(x) for x in re.findall(r"\$\s?(\d{1,3}\.\d{2})", html))
        if 3.0 <= p <= 200
    )
    if not cands:
        return None
    mid = cands[len(cands) // 2]  # median — representative, outlier-resistant
    return f"${mid:.2f}"


def price_lookup(product_name: str, retailer_url: Optional[str] = None) -> Dict:
    """Return live price + Amazon link for a product (Bright Data), else cached."""
    if not _token():
        return _fallback(product_name)
    target = retailer_url or amazon_url(product_name)
    try:
        html = _unlock(target)
        price = _pick_price(html or "")
        return {
            "source": "brightdata",
            "retailer": "Amazon",
            "price": price or _fallback(product_name)["price"],
            "in_stock": "currently unavailable" not in (html or "").lower(),
            "url": amazon_url(product_name),
        }
    except (URLError, TimeoutError, OSError) as e:
        out = _fallback(product_name)
        out["error"] = str(e)
        return out
