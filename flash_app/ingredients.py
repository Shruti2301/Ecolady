"""
Ingredient knowledge base + analyzer.

Maps OpenFoodFacts language-neutral ingredient ids (e.g. "en:palm-oil" ->
"palm-oil") to a purpose + health impact + environmental impact + a verdict
level. Used to produce the per-ingredient breakdown in the UI.

level: "good" | "caution" | "harmful"
"""

from typing import Dict, List

# slug -> (purpose, health_impact, env_impact, level)
DB = {
    # --- sugars / sweeteners ---
    "sugar": ("Sweetener", "High intake linked to obesity, diabetes", "Land/water-intensive cane or beet crop", "caution"),
    "glucose-syrup": ("Sweetener / texture", "Spikes blood sugar", "Processed corn/wheat derivative", "caution"),
    "high-fructose-corn-syrup": ("Cheap sweetener", "Strongly linked to metabolic disease", "Industrial corn monoculture", "harmful"),
    "aspartame": ("Artificial sweetener", "IARC 'possible carcinogen' (2023)", "Synthetic", "harmful"),
    "stevia": ("Natural sweetener", "Generally recognized as safe, zero-calorie", "Plant-derived, low impact", "good"),
    "honey": ("Natural sweetener", "Better than refined sugar in moderation", "Supports pollinators; low processing", "good"),

    # --- fats / oils ---
    "palm-oil": ("Cheap fat / texture", "High in saturated fat", "Major driver of deforestation & habitat loss", "harmful"),
    "palm-fat": ("Cheap fat", "High saturated fat", "Deforestation risk", "harmful"),
    "sunflower-oil": ("Cooking fat", "Unsaturated, OK in moderation", "Lower impact than palm", "caution"),
    "olive-oil": ("Healthy fat", "Rich in monounsaturated fat & antioxidants", "Traditional, relatively low impact", "good"),
    "coconut-oil": ("Fat / texture", "High saturated fat", "Tropical crop, moderate impact", "caution"),
    "partially-hydrogenated-oil": ("Solid fat / shelf life", "Trans fat — raises heart-disease risk", "Industrial processing", "harmful"),

    # --- proteins / dairy ---
    "milk": ("Dairy base", "Common allergen; otherwise nutritious", "Dairy has high carbon & water footprint", "caution"),
    "skimmed-milk-powder": ("Dairy solids", "Allergen", "Dairy footprint", "caution"),
    "whey-powder": ("Protein / texture", "Allergen (milk)", "Dairy by-product", "caution"),
    "egg": ("Binder / protein", "Common allergen", "Moderate footprint", "caution"),
    "soy-protein": ("Plant protein", "Nutritious; soy allergen", "Lower footprint than animal protein", "good"),

    # --- whole foods ---
    "hazelnut": ("Flavor / nut", "Nutritious; tree-nut allergen", "Tree crop, low impact", "good"),
    "almond": ("Nut", "Healthy fats & protein", "High water use but plant-based", "good"),
    "peanut": ("Nut / protein", "Common allergen; nutritious", "Low-impact legume", "good"),
    "oat": ("Whole grain", "High fiber, heart-healthy", "Low-impact grain", "good"),
    "whole-wheat": ("Whole grain", "Fiber-rich", "Lower impact than refined", "good"),
    "wheat-flour": ("Refined grain", "Lower fiber; gluten", "Staple crop", "caution"),
    "cocoa": ("Flavor", "Antioxidants; fine in moderation", "Deforestation & labor concerns if not certified", "caution"),
    "fat-reduced-cocoa": ("Flavor", "Antioxidants", "Sourcing concerns if uncertified", "caution"),
    "water": ("Solvent / base", "Inert", "None", "good"),
    "salt": ("Flavor / preservative", "Excess raises blood pressure", "Low impact", "caution"),

    # --- additives (also covered by E-number engine) ---
    "lecithin": ("Emulsifier", "Generally safe", "Often soy/sunflower derived", "good"),
    "soy-lecithin": ("Emulsifier", "Generally safe", "Soy-derived", "good"),
    "e322": ("Emulsifier (lecithin)", "Generally safe", "Plant-derived", "good"),
    "monosodium-glutamate": ("Flavor enhancer", "Sensitivity reports in some people", "Synthetic/fermented", "caution"),
    "e621": ("Flavor enhancer (MSG)", "Sensitivity reports", "Fermentation-derived", "caution"),
    "sodium-nitrite": ("Curing preservative", "Nitrosamine / cancer risk", "Synthetic", "harmful"),
    "e250": ("Curing preservative", "Nitrosamine risk", "Synthetic", "harmful"),
    "vanillin": ("Flavor", "Safe in food amounts", "Often synthetic", "caution"),
    "natural-flavouring": ("Flavor", "Vague; usually safe", "Variable sourcing", "caution"),
    "flavouring": ("Flavor", "Vague label", "Variable", "caution"),

    # --- common cosmetic chemicals (for makeup/personal-care scans) ---
    "paraben": ("Preservative", "Endocrine-disruption concerns", "Persists in waterways", "harmful"),
    "sodium-lauryl-sulfate": ("Foaming agent", "Skin/eye irritant", "Aquatic toxicity", "caution"),
    "microplastic": ("Texture / exfoliant", "Bioaccumulation concerns", "Persistent ocean pollution", "harmful"),
    "fragrance": ("Scent", "Common allergen; undisclosed mix", "Variable", "caution"),
    "glycerin": ("Humectant", "Generally safe", "Can be plant-derived", "good"),
    "shea-butter": ("Emollient", "Skin-nourishing", "Plant-derived, supports communities", "good"),
}

LEVEL_WEIGHT = {"good": 0, "caution": 1, "harmful": 2}


def _slug(ing_id: str) -> str:
    return (ing_id or "").split(":", 1)[-1].lower()


def _heuristic(slug: str) -> tuple:
    """Best-effort classification for ingredients not in the DB."""
    s = slug.replace("-", " ")
    if any(k in s for k in ["palm"]):
        return ("Fat", "High saturated fat", "Deforestation risk", "harmful")
    if any(k in s for k in ["paraben", "nitrite", "nitrate", "bha", "bht", "microplastic"]):
        return ("Additive", "Flagged by health bodies", "Environmental concern", "harmful")
    if any(k in s for k in ["oil", "fat", "butter"]):
        return ("Fat / oil", "Energy-dense", "Crop-dependent footprint", "caution")
    if any(k in s for k in ["sugar", "syrup", "sweeten"]):
        return ("Sweetener", "Added sugar", "Crop-intensive", "caution")
    if any(k in s for k in ["acid", "e1", "e2", "e3", "e4", "e5", "colour", "color", "flavour", "flavor", "emulsi", "stabil", "preserv"]):
        return ("Additive", "Processing aid; usually safe in small amounts", "Synthetic", "caution")
    if any(k in s for k in ["nut", "oat", "wheat", "grain", "fruit", "vegetable", "milk", "egg", "bean", "seed", "rice", "corn", "cocoa", "salt", "water"]):
        return ("Whole-food ingredient", "Recognizable food component", "Generally lower impact", "good")
    return ("Ingredient", "No specific concern identified", "Unknown impact", "caution")


def analyze(product: Dict) -> List[Dict]:
    """Return a per-ingredient breakdown list for the product."""
    out = []
    seen = set()
    for ing in product.get("ingredients", []) or []:
        slug = _slug(ing.get("id", ""))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        purpose, health, env, level = DB.get(slug, _heuristic(slug))
        name = (ing.get("text") or slug.replace("-", " ")).strip().title()
        out.append({
            "name": name,
            "slug": slug,
            "purpose": purpose,
            "health_impact": health,
            "env_impact": env,
            "level": level,
            "vegan": ing.get("vegan"),
            "percent": round(ing["percent_estimate"], 1) if ing.get("percent_estimate") else None,
        })
    # harmful first, then caution, then good
    out.sort(key=lambda x: -LEVEL_WEIGHT[x["level"]])
    return out


def lookup(name: str) -> Dict:
    """Explain a single ingredient by name (for the ingredient search feature)."""
    slug = name.strip().lower().replace(" ", "-")
    purpose, health, env, level = DB.get(slug, _heuristic(slug))
    return {
        "name": name.strip().title(),
        "purpose": purpose,
        "health_impact": health,
        "env_impact": env,
        "level": level,
    }
