"""
Health + Eco scoring for food products.

This module is pure-Python and dependency-free so it runs identically:
  - locally (the demo orchestrator), and
  - inside the Flash GPU endpoint (after the embedding step).

Inputs come from OpenFoodFacts-shaped product dicts. Scoring blends:
  - Nutri-Score (A-E)            -> nutrition quality
  - NOVA group (1-4)            -> ultra-processing
  - Eco-Score (A-E)            -> environmental impact
  - A curated additive/ingredient hazard list (controversial additives)
"""

from typing import Dict, List, Optional

# Additives commonly flagged by health bodies / consumer groups.
# code -> (human name, severity 1-3, why)
HAZARD_ADDITIVES = {
    "e102": ("Tartrazine", 2, "Azo dye linked to hyperactivity in children"),
    "e110": ("Sunset Yellow", 2, "Azo dye, hyperactivity concerns"),
    "e129": ("Allura Red", 2, "Azo dye, hyperactivity concerns"),
    "e133": ("Brilliant Blue", 1, "Synthetic dye"),
    "e150d": ("Caramel IV", 1, "May contain 4-MEI"),
    "e211": ("Sodium Benzoate", 2, "Forms benzene with vitamin C"),
    "e220": ("Sulphur Dioxide", 2, "Allergen / asthma trigger"),
    "e250": ("Sodium Nitrite", 3, "Cured-meat preservative, nitrosamine risk"),
    "e251": ("Sodium Nitrate", 3, "Nitrosamine risk"),
    "e320": ("BHA", 3, "Possible carcinogen (IARC 2B)"),
    "e321": ("BHT", 2, "Endocrine concerns in animal studies"),
    "e621": ("MSG", 1, "Flavour enhancer, sensitivity reports"),
    "e951": ("Aspartame", 2, "Sweetener, IARC possible carcinogen 2023"),
    "e171": ("Titanium Dioxide", 3, "Banned in EU 2022, genotoxicity"),
}

# Keyword hazards for products where additive codes aren't parsed.
# Multilingual because OpenFoodFacts ingredient text is often non-English.
HAZARD_KEYWORDS = {
    "palm oil": (2, "Deforestation / saturated fat"),
    "huile de palme": (2, "Palm oil — deforestation / saturated fat"),
    "aceite de palma": (2, "Palm oil — deforestation / saturated fat"),
    "palmöl": (2, "Palm oil — deforestation / saturated fat"),
    "high fructose corn syrup": (3, "Linked to metabolic disease"),
    "partially hydrogenated": (3, "Trans fat"),
    "aspartame": (2, "Sweetener, possible carcinogen"),
    "monosodium glutamate": (1, "Flavour enhancer"),
}

# Neutral analysis tags OFF computes regardless of label language.
ANALYSIS_HAZARDS = {
    "en:palm-oil": ("Palm oil", 2, "Deforestation / saturated fat"),
}

GRADE_BANDS = [
    (85, "A", "Excellent"),
    (70, "B", "Good"),
    (50, "C", "Fair"),
    (30, "D", "Poor"),
    (0,  "E", "Avoid"),
]

NUTRI_POINTS = {"a": 100, "b": 75, "c": 50, "d": 25, "e": 5}
ECO_POINTS = {"a": 100, "b": 80, "c": 55, "d": 30, "e": 10}
NOVA_PENALTY = {1: 0, 2: 8, 3: 20, 4: 35}


def _band(score: float):
    for cutoff, letter, label in GRADE_BANDS:
        if score >= cutoff:
            return letter, label
    return "E", "Avoid"


# Map every synonym (additive code, analysis tag, keyword) to one canonical
# concept so a hazard is flagged at most once regardless of how it's detected.
CONCEPT = {
    "e320": "palm", "e321": "bht",
    "e150d": "caramel", "e211": "benzoate", "e220": "sulphur",
    "e250": "nitrite", "e251": "nitrite", "e102": "tartrazine",
    "e110": "sunset", "e129": "allura", "e133": "blue",
    "e621": "msg", "e951": "aspartame", "e171": "titanium",
    "en:palm-oil": "palm",
    "palm oil": "palm", "huile de palme": "palm",
    "aceite de palma": "palm", "palmöl": "palm",
    "monosodium glutamate": "msg",
    "aspartame": "aspartame",
    "high fructose corn syrup": "hfcs",
    "partially hydrogenated": "transfat",
}


def find_hazards(product: Dict) -> List[Dict]:
    """Return list of flagged additives/ingredients, deduped by concept."""
    flagged = []
    concepts = set()

    def add(name, code, sev, why, concept):
        if concept in concepts:
            return
        concepts.add(concept)
        flagged.append({"name": name, "code": code, "severity": sev, "why": why})

    for code in product.get("additives_tags", []) or []:
        key = code.replace("en:", "").lower()
        if key in HAZARD_ADDITIVES:
            name, sev, why = HAZARD_ADDITIVES[key]
            add(name, key.upper(), sev, why, CONCEPT.get(key, key))

    for tag in product.get("ingredients_analysis_tags", []) or []:
        if tag in ANALYSIS_HAZARDS:
            name, sev, why = ANALYSIS_HAZARDS[tag]
            add(name, "", sev, why, CONCEPT.get(tag, tag))

    text = (product.get("ingredients_text", "") or "").lower()
    for kw, (sev, why) in HAZARD_KEYWORDS.items():
        if kw in text:
            concept = CONCEPT.get(kw, kw)
            label = "Palm oil" if concept == "palm" else kw.split(" (")[0].title()
            add(label, "", sev, why, concept)

    flagged.sort(key=lambda x: -x["severity"])
    return flagged


def health_score(product: Dict) -> Dict:
    """Compute a 0-100 health score from Nutri-Score, NOVA, and hazards."""
    nutri = (product.get("nutriscore_grade") or "c").lower()
    base = NUTRI_POINTS.get(nutri, 50)

    nova = product.get("nova_group")
    try:
        nova = int(nova)
    except (TypeError, ValueError):
        nova = 3
    base -= NOVA_PENALTY.get(nova, 20)

    hazards = find_hazards(product)
    hazard_penalty = sum(h["severity"] * 6 for h in hazards)
    score = max(0, min(100, base - hazard_penalty))

    letter, label = _band(score)
    return {
        "score": round(score),
        "grade": letter,
        "label": label,
        "nutriscore": nutri.upper(),
        "nova_group": nova,
        "hazards": hazards,
    }


def eco_score(product: Dict) -> Dict:
    eco = (product.get("ecoscore_grade") or "").lower()
    if eco in ECO_POINTS:
        score = ECO_POINTS[eco]
    else:
        # Fallback heuristic from packaging + palm oil
        score = 60
        if product.get("ingredients_from_palm_oil_n", 0):
            score -= 25
        pkg = (product.get("packaging", "") or "").lower()
        if "plastic" in pkg:
            score -= 15
        if "glass" in pkg or "carton" in pkg:
            score += 10
        score = max(0, min(100, score))
    letter, label = _band(score)
    return {"score": round(score), "grade": letter, "label": label}


# Rough cradle-to-shelf carbon intensity (kg CO2e per kg) by category keyword,
# used only for a relative, clearly-estimated footprint badge.
CARBON_BY_KEYWORD = [
    ("beef", 27), ("meat", 12), ("cheese", 13), ("chocolate", 19),
    ("butter", 12), ("coffee", 17), ("palm", 8), ("dairy", 6),
    ("spread", 6), ("snack", 5), ("biscuit", 4), ("cookie", 4),
    ("chip", 4), ("soda", 1.0), ("cola", 1.0), ("beverage", 0.9),
    ("water", 0.3), ("oat", 1.6), ("cereal", 2.5), ("vegetable", 1.0),
    ("fruit", 1.1), ("nut", 2.3),
]


def _flags(product: Dict) -> Dict[str, bool]:
    labels = set(product.get("labels_tags", []) or [])
    analysis = set(product.get("ingredients_analysis_tags", []) or [])
    text = (product.get("ingredients_text", "") or "").lower()
    pkg = " ".join([
        product.get("packaging", "") or "",
        " ".join(product.get("packaging_tags", []) or []),
    ]).lower()

    palm = "en:palm-oil" in analysis or "palm" in text or bool(product.get("ingredients_from_palm_oil_n"))
    palm_free = "en:palm-oil-free" in analysis or "en:palm-oil-free" in labels
    return {
        "vegan": "en:vegan" in labels or "en:vegan" in analysis,
        "vegetarian": "en:vegetarian" in labels or "en:vegetarian" in analysis,
        "non_vegan": "en:non-vegan" in analysis,
        "cruelty_free": "en:cruelty-free" in labels or "en:no-tested-on-animals" in labels,
        "organic": any("organic" in l for l in labels),
        "fair_trade": any("fair-trade" in l or "fairtrade" in l for l in labels),
        "palm_oil": palm and not palm_free,
        "palm_oil_free": palm_free,
        "microplastics": "microplastic" in text or "polyethylene" in text,
        "recyclable_packaging": ("glass" in pkg or "carton" in pkg or "paper" in pkg
                                 or "aluminium" in pkg or "recycl" in pkg) and "plastic" not in pkg,
        "plastic_packaging": "plastic" in pkg,
    }


def carbon_estimate(product: Dict) -> Dict:
    """Relative, clearly-estimated carbon footprint (kg CO2e per kg)."""
    cats = (product.get("categories", "") or "").lower()
    kg = 3.0
    for kw, val in CARBON_BY_KEYWORD:
        if kw in cats:
            kg = val
            break
    if _flags(product)["palm_oil"]:
        kg += 2
    band = "low" if kg <= 2 else "medium" if kg <= 7 else "high"
    return {"kg_co2e_per_kg": round(kg, 1), "band": band}


def sustainability(product: Dict) -> Dict:
    """0-100 sustainability score with a transparent factor breakdown."""
    f = _flags(product)
    e = eco_score(product)
    h = health_score(product)
    carbon = carbon_estimate(product)
    carbon_score = {"low": 90, "medium": 55, "high": 20}[carbon["band"]]

    factors = [
        {"factor": "Ingredient safety", "score": h["score"], "weight": 0.22},
        {"factor": "Environmental impact", "score": e["score"], "weight": 0.20},
        {"factor": "Carbon footprint", "score": carbon_score, "weight": 0.15},
        {"factor": "Packaging recyclability", "score": 85 if f["recyclable_packaging"] else (30 if f["plastic_packaging"] else 55), "weight": 0.12},
        {"factor": "Biodegradability", "score": 80 if not f["microplastics"] else 25, "weight": 0.10},
        {"factor": "Palm-oil free", "score": 95 if not f["palm_oil"] else 15, "weight": 0.09},
        {"factor": "Vegan", "score": 90 if f["vegan"] else (60 if f["vegetarian"] else 35), "weight": 0.06},
        {"factor": "Cruelty-free", "score": 90 if f["cruelty_free"] else 50, "weight": 0.06},
    ]
    total = round(sum(x["score"] * x["weight"] for x in factors))
    letter, label = _band(total)
    return {
        "score": total, "grade": letter, "label": label,
        "factors": factors, "flags": f, "carbon": carbon,
    }


def analyze(product: Dict, with_ingredients: bool = True) -> Dict:
    """Top-level: produce the full grade card for one product."""
    from . import ingredients as ing_mod
    h = health_score(product)
    e = eco_score(product)
    s = sustainability(product)
    # overall = sustainability-led, with health blended in
    overall = round(0.6 * s["score"] + 0.4 * h["score"])
    letter, label = _band(overall)
    card = {
        "product_name": product.get("product_name") or product.get("name") or "Unknown product",
        "brand": (product.get("brands") or "").split(",")[0].strip(),
        "barcode": product.get("code") or product.get("barcode"),
        "image": product.get("image_url") or product.get("image_front_url"),
        "categories": product.get("categories_tags_en") or product.get("categories", ""),
        "overall": {"score": overall, "grade": letter, "label": label},
        "health": h,
        "eco": e,
        "sustainability": s,
    }
    if with_ingredients:
        card["ingredients"] = ing_mod.analyze(product)
    return card
