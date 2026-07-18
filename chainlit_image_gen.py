"""Generator grafik social-media dla Chainlit przez OpenRouter (Nano Banana 2 / Gemini 3 Pro Image).

Komenda `/grafika <temat>` w czacie → wybór formatu (kwadrat/pion/poziom) → grafika
fotorealistyczna z tekstem na temat + logo Actio nakładane post-process.
"""
from __future__ import annotations

import base64
import io
import json
import os
import pathlib
from pathlib import Path

import httpx
from PIL import Image

# Formaty: nazwa → (ratio, width, height, aspect_str, opis)
FORMATS = {
    "kwadrat": {
        "label": "Kwadrat 1:1",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "use_case": "Instagram feed, Facebook feed, LinkedIn post",
    },
    "pion": {
        "label": "Pion 4:5",
        "width": 1080,
        "height": 1350,
        "aspect": "4:5",
        "use_case": "Instagram feed (portrait), Facebook feed (portrait)",
    },
    "poziom": {
        "label": "Poziom 1.91:1",
        "width": 1200,
        "height": 630,
        "aspect": "1.91:1",
        "use_case": "Facebook share, LinkedIn link preview, Open Graph",
    },
    "rolka": {
        "label": "Rolka 9:16",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "use_case": "TikTok, Instagram Reels, Facebook Reels, IG/FB Stories, YouTube Shorts",
    },
}

# Logo Actio – cache lokalnie (raz pobrany, potem reuse)
_LOGO_URL = "https://actio.pl/wp-content/uploads/2025/09/ACTIO-LOGO-PODSTAWOWE-BEZ-TLA.webp"
_LOGO_CACHE = Path(__file__).parent / ".chainlit" / "actio_logo_cache.png"


def _get_logo() -> Image.Image:
    """Pobierz + cache logo Actio jako PIL Image (RGBA)."""
    if not _LOGO_CACHE.exists():
        _LOGO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(_LOGO_URL, timeout=30.0, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        img.save(_LOGO_CACHE, "PNG")
    return Image.open(_LOGO_CACHE).convert("RGBA")


def _build_prompt(topic: str, fmt: dict) -> str:
    """System prompt dla Gemini 3 Pro Image (Nano Banana 2) – fotorealistyczne zdjęcie z tekstem."""
    return (
        f"Generate a photorealistic professional photograph related to: \"{topic}\".\n\n"
        f"Visual style:\n"
        f"- High-quality DSLR or commercial business photography\n"
        f"- Natural lighting or professional studio lighting\n"
        f"- Polish/European business context: modern offices, technology, professionals at work, "
        f"telecommunications infrastructure, mobile/desktop devices\n"
        f"- Rule of thirds composition, shallow depth of field where appropriate\n"
        f"- Realistic skin tones if people are present, no over-processing\n\n"
        f"Text overlay (IMPORTANT):\n"
        f"- Include a short Polish headline (3-7 words) related to the topic\n"
        f"- Use a modern sans-serif font (similar to Mulish or Inter)\n"
        f"- High contrast against background, positioned in negative space\n"
        f"- The text must be clearly readable, professional, no typos\n\n"
        f"Technical:\n"
        f"- Aspect ratio: {fmt['aspect']} (target {fmt['width']}x{fmt['height']}px)\n"
        f"- Keep the bottom-right corner free of faces, text and key subjects (a small logo will be "
        f"composited there in post-processing), but the photo MUST continue naturally into that corner - "
        f"do NOT paint any box, white plate, placeholder, empty panel or frame there\n\n"
        f"AVOID:\n"
        f"- White boxes, blank plates, placeholder rectangles or empty panels anywhere in the image\n"
        f"- Cartoon, illustration, 3D render, anime, watercolor styles\n"
        f"- Any visible brand logos, watermarks, or company names other than what's specified\n"
        f"- Stock-photo-look cheesy compositions, fake handshakes, exaggerated expressions\n"
        f"- Oversaturated colors, HDR look, composite/photoshopped feel\n"
        f"- Text errors, garbled letters, illegible fonts"
    )


def _call_nano_banana(prompt: str) -> bytes:
    """Wywołanie OpenRouter z modelem image generation. Zwraca raw bytes obrazka."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    # Preferujemy Nano Banana 2 Pro jeśli dostępne, inaczej fallback do dostępnego image modelu
    model = os.environ.get("CHAINLIT_IMAGE_MODEL") or os.environ.get("AUTOPOST_IMAGE_MODEL", "google/gemini-3-pro-image-preview")

    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Chainlit",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "provider": {"data_collection": "deny"},
        },
        timeout=180.0,
    )
    r.raise_for_status()
    data = r.json()

    images = data.get("choices", [{}])[0].get("message", {}).get("images") or []
    if not images:
        raise RuntimeError(f"OpenRouter zwrócił brak images. Response: {json.dumps(data)[:500]}")

    url = images[0].get("image_url", {}).get("url", "")
    if url.startswith("data:image/"):
        b64 = url.split(",", 1)[1]
        return base64.b64decode(b64)
    elif url.startswith("http"):
        return httpx.get(url, timeout=60.0).content
    raise RuntimeError(f"Nieoczekiwany format URL: {url[:80]}")


def _add_logo_overlay(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """Nałóż logo Actio w prawym dolnym rogu + ewentualnie wymuś docelowe wymiary."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Resize/crop do docelowych wymiarów (jeśli model wygenerował lekko inny)
    if base.size != (target_w, target_h):
        base = base.resize((target_w, target_h), Image.LANCZOS)

    logo = _get_logo()
    # Logo szerokie ~15% szerokości grafiki
    logo_target_w = int(target_w * 0.15)
    logo_target_h = int(logo.height * (logo_target_w / logo.width))
    logo_resized = logo.resize((logo_target_w, logo_target_h), Image.LANCZOS)

    # Padding bottom-right
    padding = max(20, int(target_w * 0.025))
    pos_x = target_w - logo_target_w - padding
    pos_y = target_h - logo_target_h - padding

    # Semi-transparent rounded-rectangle background pod logo (czytelność).
    # Wymiar ZAWSZE = logo + bg_padding (~10px) - wieksze biale pola na starych grafikach
    # malowal model przez stary prompt "leave clear space" (usuniete 18.07).
    from PIL import ImageDraw
    bg_padding = int(padding * 0.4)
    bg_w, bg_h = logo_target_w + 2 * bg_padding, logo_target_h + 2 * bg_padding
    bg = Image.new("RGBA", (bg_w, bg_h), (0, 0, 0, 0))
    _d = ImageDraw.Draw(bg)
    _d.rounded_rectangle([0, 0, bg_w - 1, bg_h - 1], radius=max(8, bg_padding), fill=(255, 255, 255, 215))
    base.paste(bg, (pos_x - bg_padding, pos_y - bg_padding), bg)
    base.paste(logo_resized, (pos_x, pos_y), logo_resized)

    out = io.BytesIO()
    base.convert("RGB").save(out, "PNG", quality=92, optimize=True)
    return out.getvalue()


def generate_social_image(topic: str, format_key: str, output_dir: Path | str | None = None) -> Path:
    """Wygeneruj grafikę social na temat `topic` w wybranym formacie. Zwraca ścieżkę do PNG."""
    if format_key not in FORMATS:
        raise ValueError(f"Nieznany format: {format_key}. Dostępne: {list(FORMATS.keys())}")
    fmt = FORMATS[format_key]

    prompt = _build_prompt(topic, fmt)
    raw = _call_nano_banana(prompt)
    final_bytes = _add_logo_overlay(raw, fmt["width"], fmt["height"])

    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic[:40]).strip("_")
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = output_dir / f"{safe_topic}_{format_key}_{ts}.png"
    out.write_bytes(final_bytes)
    return out
