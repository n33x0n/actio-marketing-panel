"""Image generation via OpenRouter (Nano Banana 2 / google/gemini-3-flash-image)."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx


def generate_image(prompt: str, output_path: str) -> str:
    """Generate image via OpenRouter, save to output_path. Returns path."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("AUTOPOST_IMAGE_MODEL", "google/gemini-3-flash-image")

    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Autopost",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
            "provider": {"data_collection": "deny"},
        },
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()

    images = data.get("choices", [{}])[0].get("message", {}).get("images") or []
    if not images:
        raise RuntimeError(f"OpenRouter zwrócił brak images. Response: {data}")

    url = images[0].get("image_url", {}).get("url", "")
    if url.startswith("data:image/"):
        b64 = url.split(",", 1)[1]
        raw = base64.b64decode(b64)
    elif url.startswith("http"):
        raw = httpx.get(url, timeout=60.0).content
    else:
        raise RuntimeError(f"Nieoczekiwany format URL: {url[:80]}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    return str(out)


def build_prompt(keyword: str) -> str:
    return (
        f'Professional B2B telecom illustration for a blog article about "{keyword}". '
        f"Modern minimal style, navy blue and slate gray color scheme. "
        f"Abstract tech metaphor (lines, nodes, geometric patterns). "
        f"No text in image, no people's faces, no readable logos. "
        f"Wide composition 1200x630px (Open Graph format). Clean professional look."
    )
