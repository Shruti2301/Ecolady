"""
Server-side OCR for product packaging.

Uses RapidOCR (ONNX, CPU-friendly, far more accurate on photos than
browser Tesseract). Returns the full text PLUS a ranked "product guess"
built from the most prominent text lines (largest, highest-confidence),
which is what we actually want to search the product catalog with.

On the Flash GPU endpoint this is swapped for EasyOCR on CUDA (see
endpoints.py) for higher accuracy / throughput; the interface is the same.
"""

import io
import re
from typing import Dict, List

_ENGINE = None

# noisy tokens that are never a product/brand name
_STOP = {
    "ingredients", "nutrition", "facts", "net", "wt", "weight", "contains",
    "may", "produced", "manufactured", "distributed", "best", "before",
    "serving", "size", "per", "kcal", "energy", "www", "com", "ltd", "inc",
}


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def _preprocess(image_bytes: bytes) -> bytes:
    """Upscale small images and boost contrast — helps OCR on phone photos."""
    try:
        from PIL import Image, ImageOps, ImageEnhance
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = im.size
        if max(w, h) < 1400:
            scale = 1400 / max(w, h)
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        im = ImageOps.autocontrast(im, cutoff=1)
        im = ImageEnhance.Sharpness(im).enhance(1.4)
        out = io.BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return image_bytes


def _box_height(box) -> float:
    ys = [p[1] for p in box]
    return max(ys) - min(ys)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract(image_bytes: bytes) -> Dict:
    """Run OCR and return {full_text, lines, product_guess}."""
    img = _preprocess(image_bytes)
    import numpy as np
    from PIL import Image
    arr = np.array(Image.open(io.BytesIO(img)).convert("RGB"))

    result, _ = _engine()(arr)
    if not result:
        return {"full_text": "", "lines": [], "product_guess": ""}

    lines = []
    for box, text, score in result:
        t = _clean(text)
        if not t:
            continue
        lines.append({"text": t, "conf": round(float(score), 2), "h": round(_box_height(box), 1)})

    full_text = " ".join(l["text"] for l in lines)

    # --- product guess: the most prominent, brand-like lines ---
    def looks_like_name(t: str) -> bool:
        low = t.lower()
        if any(w in low for w in _STOP):
            return False
        letters = sum(c.isalpha() for c in t)
        return letters >= 3 and letters / max(len(t), 1) > 0.5

    cand = [l for l in lines if looks_like_name(l["text"])]
    guess = ""
    if cand:
        max_h = max(l["h"] for l in cand)
        # keep only the prominent lines (brand + product name), not fine print
        prominent = [l for l in cand if l["h"] >= 0.45 * max_h and l["conf"] >= 0.5]
        prominent.sort(key=lambda l: -(l["h"] * l["conf"]))
        guess = " ".join(l["text"] for l in prominent[:3])

    return {
        "full_text": full_text,
        "lines": sorted(lines, key=lambda l: -l["h"]),
        "product_guess": _clean(guess) or full_text[:60],
    }
