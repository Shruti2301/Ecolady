# 🌿 Verdant — scan consciously, choose beautifully

A romantic, eco-friendly product analyzer. Scan any product (camera · photo ·
barcode · name) → reveal its **ingredients, eco-score, and kinder alternatives**
— with live retail prices and a switch-impact comparison.

Built for the **Runpod Flash Hack Day**. Two Flash tracks at once: a
**multi-endpoint pipeline** (CPU → GPU) and **real-time inference**.

Endpoint	URL
cleancart-ocr (GPU)	https://api.runpod.ai/v2/tcr4zjzfmez3hl/runsync
cleancart-extract (CPU)	https://api.runpod.ai/v2/ogsrl80621i4om/runsync
cleancart-score (GPU)	https://api.runpod.ai/v2/r67zp9bhz9fp6v/runsync


```
 camera / photo ─┬─ Tesseract.js OCR (in-browser) ─┐
 barcode / name ─┘                                  ▼
                       CPU Flash endpoint  cleancart-extract
                       OpenFoodFacts lookup → product + ingredients
                                                    │
                                                    ▼
                       GPU Flash endpoint  cleancart-score
                       embeddings → eco score + semantic swap ranking
                                                    │
                                                    ▼
                       Bright Data Web Unlocker → live Amazon price
                                                    │
                                                    ▼
                 grade card · ingredient analysis · swaps · compare
```

## What it does

- **4 input methods** — live webcam, image upload (drag/drop), barcode scan, name search.
- **OCR** — accurate server-side **RapidOCR** (CPU) extracts label text and ranks the
  prominent lines (brand + product name) to search with; **EasyOCR on GPU** when deployed
  to Flash. Falls back to in-browser Tesseract.js (with preprocessing) if the server is down.
- **Ingredient analysis** — every ingredient with purpose, health impact, env impact, vegan flag, %.
- **Eco-score 0–100** — circular gauge + 8-factor breakdown (safety, carbon, packaging,
  biodegradability, palm-oil, vegan, cruelty-free…) + badges + estimated carbon footprint.
- **Sustainable alternatives** — same-category, embedding-ranked, with eco-score, key
  ingredients, **live Amazon price**, CO₂ reduction %, packaging improvement, and why-it's-better.
- **Shopping** — Amazon link, dummy Add-to-Cart, Compare, View Details.
- **Compare view** — yearly savings switching products (CO₂, plastic, water, additives) + bar charts.
- **Extras** — scan history & favorites (localStorage), dark/light theme, responsive, reduced-motion a11y.

Real data via [OpenFoodFacts](https://world.openfoodfacts.org) (free, no auth).

## Run (local — no GPU needed)

```bash
cd runpodhackathonv1
# uses Python 3.10+ (runpod-flash needs it); venv already built with 3.12
.venv/bin/python server.py     # → http://localhost:8000
```

Camera + OCR work on `localhost` (treated as a secure context). Keys in `.env`
are loaded automatically; without them, prices fall back to cached values.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/scan` `{barcode\|name}` | full grade card (ingredients, swaps, tips) |
| `POST /api/analyze-text` `{text}` | OCR text → matched product → full card |
| `POST /api/price` `{name}` | live Bright Data Amazon price (lazy, per swap) |
| `POST /api/compare` `{barcode, alt_barcode}` | switch-impact savings |
| `POST /api/ingredient` `{name}` | explain a single ingredient |
| `GET  /api/health` | mode + whether Bright Data / RunPod keys are set |

## Deploy to Runpod Flash

```bash
set -a && . ./.env && set +a       # loads RUNPOD_API_KEY
.venv/bin/flash deploy             # provisions cleancart-extract (CPU) + cleancart-score (GPU)
USE_FLASH=1 .venv/bin/python server.py   # route /api/scan through the deployed endpoints
```

## Layout

| Path | What |
|---|---|
| `endpoints.py` | Flash `@Endpoint`s: CPU `extract` + GPU `score` + orchestrator |
| `server.py` | FastAPI orchestrator + web host (auto-loads `.env`) |
| `flash_app/scoring.py` | health + sustainability scoring, hazard engine, carbon estimate |
| `flash_app/ingredients.py` | ingredient knowledge base + per-ingredient analyzer |
| `flash_app/recommend.py` | embedding-ranked swaps (CO₂, why-better, Amazon link) |
| `flash_app/openfoodfacts.py` | product lookup + in-category candidate pool |
| `flash_app/brightdata.py` | Bright Data Web Unlocker price scraping (+ fallback) |
| `flash_app/impact.py` | switch-impact savings + sustainability tips |
| `web/` | Verdant single-page UI (romantic eco theme, glassmorphism) |

## 3-minute demo script

1. Search **Nutella** → eco **E**, palm-oil flagged, ingredient breakdown → grade-**A** almond-butter swaps with live prices.
2. Hit **Compare** on a swap → “switching saves ~130 kg CO₂/yr, cuts additives.”
3. **Upload** a label photo → OCR reads it → auto-analyzes.
4. Search **Quaker Oats** → eco **A**, “already a strong pick.”
5. Terminal: `flash deploy` + the CPU→GPU split in `endpoints.py`.
