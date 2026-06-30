"""
Switch-impact estimator + sustainability tips.

Given an original product and a chosen alternative, estimate the per-year
environmental savings from switching (illustrative, clearly-estimated numbers
suitable for a demo comparison view).
"""

from typing import Dict, List

from . import scoring


def switch_impact(orig_card: Dict, alt_card: Dict, units_per_year: int = 52) -> Dict:
    """Estimate yearly savings switching from orig -> alt (one unit/week)."""
    of = orig_card["sustainability"]["flags"]
    af = alt_card["sustainability"]["flags"]
    o_c = orig_card["sustainability"]["carbon"]["kg_co2e_per_kg"]
    a_c = alt_card["sustainability"]["carbon"]["kg_co2e_per_kg"]

    # assume ~0.4 kg per unit
    kg_per_unit = 0.4
    carbon_saved = max(0, round((o_c - a_c) * kg_per_unit * units_per_year, 1))

    plastic_saved = 0
    if of["plastic_packaging"] and af["recyclable_packaging"]:
        plastic_saved = round(0.03 * units_per_year * 1000)  # grams/year

    # crude water proxy: dirtier products (lower eco) ~ more water
    water_saved = max(0, round((alt_card["sustainability"]["score"] -
                                orig_card["sustainability"]["score"]) * 2 * units_per_year))

    chemicals_cut = max(0, len(orig_card["health"]["hazards"]) - len(alt_card["health"]["hazards"]))

    return {
        "carbon_saved_kg": carbon_saved,
        "plastic_saved_g": plastic_saved,
        "water_saved_l": water_saved,
        "harmful_chemicals_cut": chemicals_cut,
        "eco_score_gain": alt_card["sustainability"]["score"] - orig_card["sustainability"]["score"],
        "metrics": [
            {"label": "Carbon", "orig": o_c, "alt": a_c, "unit": "kg CO₂e/kg", "lower_better": True},
            {"label": "Eco score", "orig": orig_card["sustainability"]["score"],
             "alt": alt_card["sustainability"]["score"], "unit": "/100", "lower_better": False},
            {"label": "Flagged additives", "orig": len(orig_card["health"]["hazards"]),
             "alt": len(alt_card["health"]["hazards"]), "unit": "", "lower_better": True},
        ],
    }


TIPS = {
    "palm": "Look for 'RSPO certified' or palm-oil-free labels to curb deforestation.",
    "spread": "Nut butters with a single ingredient (just nuts) skip added sugar and palm oil.",
    "cola": "Swap one soda a day for sparkling water to cut sugar and packaging waste.",
    "soda": "Buy concentrates or larger formats to reduce per-serving plastic.",
    "snack": "Choose baked over fried and recyclable cartons over multilayer plastic.",
    "chocolate": "Pick Fairtrade / organic cocoa to support lower-impact farming.",
    "default": "Favor short ingredient lists, recyclable packaging, and certified labels.",
}


def tips_for(product: Dict) -> List[str]:
    cats = (product.get("categories", "") or "").lower()
    out = []
    for key, tip in TIPS.items():
        if key != "default" and key in cats:
            out.append(tip)
    if scoring.find_hazards(product):
        out.append("This product has flagged additives — check the breakdown below.")
    out.append(TIPS["default"])
    return out[:3]
