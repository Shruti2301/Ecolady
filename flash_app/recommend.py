"""
Healthier-swap recommender.

Given a scanned product, find products in the same category that score
strictly better on health, ranked by semantic similarity to the original
(so a swap actually resembles what the user wanted).

The embedding step is pluggable:
  - GPU Flash endpoint  -> sentence-transformers (real model inference)
  - local fallback      -> lightweight token-overlap similarity

This keeps the demo running without the heavy model while the deployed
Flash version does genuine GPU embedding inference.
"""

import math
from typing import Dict, List, Optional

from . import scoring, openfoodfacts, brightdata


def _tokens(text: str) -> set:
    return {t for t in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split() if len(t) > 2}


def _fallback_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_EMBEDDER = None


def _get_embedder():
    """Lazy-load sentence-transformers if available (GPU endpoint)."""
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER
    try:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        _EMBEDDER = False  # mark as unavailable
    return _EMBEDDER


def _embed_similarity(query: str, candidates: List[str]) -> List[float]:
    model = _get_embedder()
    if not model:
        return [_fallback_similarity(query, c) for c in candidates]
    import numpy as np
    vecs = model.encode([query] + candidates, normalize_embeddings=True)
    q, cs = vecs[0], vecs[1:]
    return [float(np.dot(q, c)) for c in cs]


def _describe(product: Dict) -> str:
    return " ".join(
        str(x) for x in [
            product.get("product_name"),
            product.get("brands"),
            product.get("categories"),
        ] if x
    )


def _why_better(orig_card, cand_card) -> List[str]:
    reasons = []
    of, cf = orig_card["sustainability"]["flags"], cand_card["sustainability"]["flags"]
    if of["palm_oil"] and not cf["palm_oil"]:
        reasons.append("Palm-oil free")
    if not of["vegan"] and cf["vegan"]:
        reasons.append("Fully vegan")
    if not of["organic"] and cf["organic"]:
        reasons.append("Certified organic")
    if of["plastic_packaging"] and cf["recyclable_packaging"]:
        reasons.append("Recyclable packaging")
    oh = len(orig_card["health"]["hazards"])
    ch = len(cand_card["health"]["hazards"])
    if ch < oh:
        reasons.append(f"{oh - ch} fewer flagged additive{'s' if oh - ch != 1 else ''}")
    if cand_card["health"]["grade"] < orig_card["health"]["grade"]:
        reasons.append(f"Nutri-Score {cand_card['health']['nutriscore']} vs {orig_card['health']['nutriscore']}")
    return reasons[:4] or ["Higher overall eco score"]


def _packaging_text(orig_flags, cand_flags) -> str:
    if orig_flags["plastic_packaging"] and cand_flags["recyclable_packaging"]:
        return "Plastic → recyclable (glass/carton)"
    if cand_flags["recyclable_packaging"]:
        return "Recyclable packaging"
    return "Comparable packaging"


def recommend(product: Dict, top_k: int = 3) -> List[Dict]:
    """Return up to top_k healthier, more sustainable alternatives."""
    GRADE_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}

    original = scoring.analyze(product, with_ingredients=False)
    orig_score = original["health"]["score"]
    orig_rank = GRADE_RANK.get(original["health"]["grade"], 1)
    orig_carbon = original["sustainability"]["carbon"]["kg_co2e_per_kg"]

    pool = openfoodfacts.candidate_pool(product, limit=24)

    candidates, descs = [], []
    for cand in pool:
        if not cand.get("product_name") or cand.get("code") == product.get("code"):
            continue
        card = scoring.analyze(cand, with_ingredients=False)
        # only show a strictly better grade letter (a real, defensible swap)
        if GRADE_RANK.get(card["health"]["grade"], 1) <= orig_rank:
            continue
        candidates.append((cand, card))
        descs.append(_describe(cand))

    if not candidates:
        return []

    sims = _embed_similarity(_describe(product), descs)
    ranked = sorted(
        zip(candidates, sims),
        key=lambda x: (x[0][1]["sustainability"]["score"], x[1]),
        reverse=True,
    )

    out = []
    for (cand, card), sim in ranked[:top_k]:
        cand_carbon = card["sustainability"]["carbon"]["kg_co2e_per_kg"]
        co2_red = max(0, round((orig_carbon - cand_carbon) / max(orig_carbon, 0.1) * 100))
        out.append({
            "product_name": card["product_name"],
            "brand": card["brand"],
            "barcode": card["barcode"],
            "image": card["image"],
            "eco_score": card["sustainability"]["score"],
            "eco_grade": card["sustainability"]["grade"],
            "health_grade": card["health"]["grade"],
            "health_score": card["health"]["score"],
            "key_ingredients": [i["name"] for i in scoring.find_hazards(cand)][:3]
                               or [card["categories"].split(",")[0].strip() if card["categories"] else "Whole-food based"],
            "improvement": card["sustainability"]["score"] - original["sustainability"]["score"],
            "co2_reduction_pct": co2_red,
            "packaging": _packaging_text(original["sustainability"]["flags"], card["sustainability"]["flags"]),
            "why_better": _why_better(original, card),
            "similarity": round(sim, 3),
            "amazon_url": brightdata.amazon_url(card["product_name"]),
        })
    return out
