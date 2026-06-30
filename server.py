"""
Local demo orchestrator for CleanCart / EcoLume.

Runs the SAME pipeline functions the Flash endpoints run, but in-process, so
the demo works on a laptop with no GPU and no Flash login. Serves the web UI.

    python server.py        ->  http://localhost:8000

Loads .env automatically (RUNPOD_API_KEY, BRIGHTDATA_API_TOKEN, BRIGHTDATA_ZONE).
Set USE_FLASH=1 to route /api/scan through the deployed Flash endpoints.
"""

import os


# --- load .env before importing modules that read env at import time ---
def _load_env():
    path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from flash_app import scoring, recommend, openfoodfacts, brightdata, ingredients, impact

app = FastAPI(title="CleanCart")

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
USE_FLASH = os.environ.get("USE_FLASH") == "1"


class ScanReq(BaseModel):
    barcode: str | None = None
    name: str | None = None


class TextReq(BaseModel):
    text: str


class OcrReq(BaseModel):
    image: str  # data URL or base64-encoded image


class IngredientReq(BaseModel):
    name: str


class PriceReq(BaseModel):
    name: str


class CompareReq(BaseModel):
    barcode: str
    alt_barcode: str


def _resolve(barcode=None, name=None):
    product = None
    if barcode:
        product = openfoodfacts.lookup_barcode(barcode)
    if product is None and name:
        results = openfoodfacts.search(name, limit=1)
        product = results[0] if results else None
    return product


def _full_card(product):
    # Prices are fetched lazily by the client (/api/price) so the scan returns
    # fast — a single Bright Data unlock takes ~10s, and we have 3 swaps.
    card = scoring.analyze(product)
    card["swaps"] = recommend.recommend(product, top_k=3)
    card["tips"] = impact.tips_for(product)
    return card


@app.post("/api/scan")
async def scan(req: ScanReq):
    if USE_FLASH:
        from endpoints import analyze_pipeline
        return JSONResponse(await analyze_pipeline(barcode=req.barcode, name=req.name))
    product = _resolve(req.barcode, req.name)
    if product is None:
        return JSONResponse({"error": "Product not found", "barcode": req.barcode, "name": req.name})
    return JSONResponse(_full_card(product))


@app.post("/api/analyze-text")
def analyze_text(req: TextReq):
    """Take raw OCR text from a scanned label, find the product, analyze it."""
    text = (req.text or "").strip()
    if not text:
        return JSONResponse({"error": "No text detected"})
    words = [w for w in "".join(c if c.isalnum() else " " for c in text).split() if len(w) > 2]
    query = " ".join(words[:8]) or text[:60]
    results = openfoodfacts.search(query, limit=1)
    if not results:
        return JSONResponse({"error": "No matching product found", "query": query, "ocr_text": text})
    card = _full_card(results[0])
    card["ocr_text"] = text
    card["matched_query"] = query
    return JSONResponse(card)


@app.post("/api/ocr")
def ocr_scan(req: OcrReq):
    """Server-side OCR (RapidOCR): image -> prominent text -> matched product."""
    import base64
    from flash_app import ocr
    raw = req.image.split(",", 1)[-1] if req.image.startswith("data:") else req.image
    try:
        image_bytes = base64.b64decode(raw)
    except Exception:
        return JSONResponse({"error": "Could not decode image"})
    res = ocr.extract(image_bytes)
    guess = res.get("product_guess") or res.get("full_text", "")
    if not guess:
        return JSONResponse({"error": "No text detected in image", "ocr": res})
    results = openfoodfacts.search(guess, limit=1)
    if not results:
        return JSONResponse({"error": "No matching product found",
                             "ocr_text": res["full_text"], "product_guess": guess})
    card = _full_card(results[0])
    card["ocr_text"] = res["full_text"]
    card["matched_query"] = guess
    card["ocr_lines"] = res["lines"][:8]
    return JSONResponse(card)


@app.post("/api/ingredient")
def ingredient(req: IngredientReq):
    return JSONResponse(ingredients.lookup(req.name))


@app.post("/api/price")
def price(req: PriceReq):
    """Live retail price + Amazon link via Bright Data (lazy, per swap)."""
    return JSONResponse(brightdata.price_lookup(req.name))


@app.post("/api/compare")
def compare(req: CompareReq):
    a = _resolve(barcode=req.barcode)
    b = _resolve(barcode=req.alt_barcode)
    if not a or not b:
        return JSONResponse({"error": "One or both products not found"})
    ca, cb = scoring.analyze(a), scoring.analyze(b)
    return JSONResponse({
        "original": {"name": ca["product_name"], "score": ca["sustainability"]["score"]},
        "alternative": {"name": cb["product_name"], "score": cb["sustainability"]["score"]},
        "impact": impact.switch_impact(ca, cb),
    })


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": "flash" if USE_FLASH else "local",
        "brightdata": bool(os.environ.get("BRIGHTDATA_API_TOKEN")),
        "runpod": bool(os.environ.get("RUNPOD_API_KEY")),
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
