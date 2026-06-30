"""
Product lookup via OpenFoodFacts (free, no auth, real data).
Falls back to a small local cache so the demo works offline / on bad wifi.
"""

import json
import os
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
SEARCH_URL = (
    "https://world.openfoodfacts.org/cgi/search.pl"
    "?search_terms={q}&search_simple=1&action=process&json=1&page_size=12"
)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CACHE = os.path.join(_DATA_DIR, "sample_products.json")

# Fields we pull back from OFF
_FIELDS = (
    "code,product_name,brands,image_url,image_front_url,nutriscore_grade,"
    "nova_group,ecoscore_grade,additives_tags,ingredients_text,categories,"
    "categories_tags,ingredients_analysis_tags,packaging,packaging_tags,"
    "ingredients_from_palm_oil_n,nutriments,ingredients,labels_tags"
)


import time

_GET_CACHE: Dict[str, Dict] = {}


def _http_get_json(url: str, timeout: float = 8.0, retries: int = 2) -> Optional[Dict]:
    if url in _GET_CACHE:
        return _GET_CACHE[url]
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "CleanCart/1.0 (hackathon; contact@cleancart.app)"})
            with urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                _GET_CACHE[url] = data
                return data
        except (URLError, TimeoutError, ValueError, OSError):
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))  # back off OFF rate limits
    return None


def _load_cache() -> Dict:
    try:
        with open(_CACHE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"products": {}, "catalog": []}


def lookup_barcode(barcode: str) -> Optional[Dict]:
    """Return a normalized product dict for a barcode, or None."""
    barcode = str(barcode).strip()
    data = _http_get_json(OFF_URL.format(barcode=barcode) + f"?fields={_FIELDS}")
    if data and data.get("status") == 1:
        p = data["product"]
        p["code"] = barcode
        return p

    # offline / unknown -> cache
    cache = _load_cache()
    if barcode in cache.get("products", {}):
        return cache["products"][barcode]
    return None


def search(query: str, limit: int = 12) -> list:
    """Search products by name (used to build the alternatives pool)."""
    from urllib.parse import quote
    data = _http_get_json(SEARCH_URL.format(q=quote(query)))
    if data and data.get("products"):
        return data["products"][:limit]
    cache = _load_cache()
    return cache.get("catalog", [])[:limit]


CAT_SEARCH = (
    "https://world.openfoodfacts.org/api/v2/search"
    "?categories_tags={tag}&fields={fields}&page_size={n}"
    "&sort_by=nutriscore_score"  # healthiest (Nutri a) first
)


def candidate_pool(product: Dict, limit: int = 24) -> list:
    """Build a same-category alternatives pool via OFF's v2 category search.

    We iterate the product's English category tags from most-specific to
    general, pulling in-category products sorted by Nutri-Score (best first),
    and dedupe by barcode. This keeps swaps in the SAME category (no soda ->
    almond-butter cross-contamination) and is far more reliable than text
    search. Returns [] if nothing is found rather than unrelated fallbacks.
    """
    tags = [
        t[3:] for t in (product.get("categories_tags") or [])
        if t.startswith("en:") and t[3:].isascii()
    ]
    # most-specific first; only the 3 most-specific tags so we don't drift
    # into broad buckets like "breakfasts" that pull mis-categorized junk
    tags = list(reversed(tags))[:3]

    # Pull the healthiest slice from EACH tag (each query is sorted best-first),
    # so a broad-but-relevant tag like "spreads" still contributes its grade-A
    # options instead of being crowded out by a worse-but-more-specific tag.
    per_tag = max(8, limit // max(1, len(tags)))
    pool, seen = [], {product.get("code")}
    for tag in tags:
        url = CAT_SEARCH.format(tag=tag, fields=_FIELDS, n=per_tag)
        data = _http_get_json(url)
        for cand in (data or {}).get("products", []) or []:
            code = cand.get("code")
            grade = (cand.get("nutriscore_grade") or "").lower()
            if grade not in ("a", "b", "c", "d", "e"):
                continue  # skip entries without real nutrition data
            if code and code not in seen and cand.get("product_name"):
                seen.add(code)
                pool.append(cand)
    return pool[:limit]
