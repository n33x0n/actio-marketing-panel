"""Generator filmów lego-style przez Veo 3.1 (OpenRouter).

Komenda `/lego <opis sceny>` w czacie → LLM (Sonnet 4.6) enhance'uje opis w
cinematic prompt z brick-style descriptors → Veo 3.1 (OpenRouter) → mp4.

Veo 3.1 obsługuje text+image -> video, natywne audio (dialog+ambient),
1080p, durations 4/6/8s, aspect ratios 9:16 / 16:9 / 1:1.

Cena: $0.40/sec → 4s=$1.60, 6s=$2.40, 8s=$3.20.
"""
from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path

import httpx

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

VEO_TIERS = {
    "lite": {
        "model": "google/veo-3.1-lite",
        "label": "Lite ($0,05/s)",
        "price_per_sec": 0.05,
        "aspect_ratios": ["9:16", "16:9"],  # brak 1:1
        "description": "Cost-effective, dla iteracji i high-volume",
    },
    "fast": {
        "model": "google/veo-3.1-fast",
        "label": "Fast ($0,10/s)",
        "price_per_sec": 0.10,
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "description": "Mid-tier, balanced speed/quality",
    },
    "standard": {
        "model": "google/veo-3.1",
        "label": "Standard ($0,40/s)",
        "price_per_sec": 0.40,
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "description": "Maximum fidelity, production hero",
    },
}
VEO_DEFAULT_TIER = "lite"

VEO_FORMATS = {
    "shorts": {"label": "Pion 9:16", "aspect_ratio": "9:16", "use_case": "TikTok, IG Reels, YT Shorts, Stories"},
    "youtube": {"label": "Poziom 16:9", "aspect_ratio": "16:9", "use_case": "YouTube, LinkedIn, prezentacje"},
    "square": {"label": "Kwadrat 1:1", "aspect_ratio": "1:1", "use_case": "Instagram feed, Facebook feed"},
}

# Backward compat – legacy alias
VEO_MODEL = VEO_TIERS["standard"]["model"]

VEO_DURATIONS = [4, 6, 8]
VEO_DEFAULT_DURATION = 8


def formats_for_tier(tier: str) -> dict:
    """Filter VEO_FORMATS do aspect ratios obsługiwanych przez dany tier."""
    allowed = VEO_TIERS[tier]["aspect_ratios"]
    return {k: v for k, v in VEO_FORMATS.items() if v["aspect_ratio"] in allowed}


def _enhance_to_veo_prompt(scene_description: str) -> str:
    """LLM przekształca polski opis sceny w cinematic Veo prompt z brick-style descriptors."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_VEO_PROMPT_MODEL", "anthropic/claude-sonnet-4.6")

    instruction = f"""Jesteś video directorem piszącym prompt do modelu Veo 3.1 (text-to-video AI).

Opis sceny od użytkownika (po polsku):
{scene_description}

Zadanie: przekształć ten opis w pełen 1-paragraph cinematic prompt PO ANGIELSKU dla Veo 3.1.

WYMAGANIA OBOWIĄZKOWE:

1. STYL VIZUALNY: wszystkie postacie, obiekty, scenografia muszą być w stylu interlocking plastic brick minifigures (klocki konstrukcyjne). UŻYJ TYCH DESKRYPTORÓW: "blocky plastic minifigures with cylindrical hand grips", "studded plastic heads", "interlocking plastic bricks", "glossy plastic textures with visible studs", "stop-motion-style brick animation".

2. ZAKAZ TRADEMARKÓW: ZERO "LEGO", "Star Wars", "Marvel", "Minecraft" ani żadnych nazw marek. Tylko generic plastic brick aesthetic.

3. CINEMATIC DETAILS: dodaj camera angle (close-up / wide / dolly / handheld), lighting (studio softbox / dramatic / warm), depth of field, motion type.

4. AUDIO (Veo 3.1 generuje natywnie): opisz krótko sound design i mówione dialogi. Jeśli postacie mówią – cytuj exact line w cudzysłowach + opisz akcent (np. "with a warm Polish accent"). Jeśli polski dialog – podaj go DOSŁOWNIE po polsku w cudzysłowach (Veo radzi sobie z PL).

5. LONG: 80-150 słów po angielsku, jedna płynna proza (bez markdown, bez list, bez nagłówków).

Zwróć WYŁĄCZNIE finalny prompt po angielsku. Żadnego wstępu, komentarzy, cudzysłowów otaczających całość."""

    r = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Chainlit Veo Lego",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": instruction}],
            "temperature": 0.8,
            "max_tokens": 600,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _veo_create(prompt: str, duration: int, aspect_ratio: str, tier: str = VEO_DEFAULT_TIER,
                image_path: Path | str | None = None) -> tuple[str, str]:
    """POST /videos – zwraca (id, polling_url). Tier wybiera Veo Lite/Fast/Standard.

    image_path: opcjonalnie ścieżka do obrazka referencyjnego (jpg/png) – first-frame conditioning.
                Veo wykorzysta wizualne cechy do generowania spójnego output.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model_id = VEO_TIERS[tier]["model"]
    payload = {
        "model": model_id,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": "1080p",
    }
    if image_path:
        import base64
        img_bytes = Path(image_path).read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode()
        # Veo akceptuje image field jako base64. Format: image/jpeg lub image/png.
        ext = Path(image_path).suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
        payload["image"] = f"data:{mime};base64,{img_b64}"
    r = httpx.post(
        f"{OPENROUTER_BASE}/videos",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60.0,
    )
    if r.status_code not in (200, 202):
        raise RuntimeError(f"Veo create {r.status_code}: {r.text[:500]} | payload: {json.dumps(payload)[:300]}")
    j = r.json()
    return j["id"], j["polling_url"]


def _veo_poll(polling_url: str, on_progress=None, timeout_sec: int = 1800) -> str:
    """Polling co 10 sek aż video gotowe. Zwraca video_url."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    start = time.time()
    last_status = None
    while time.time() - start < timeout_sec:
        r = httpx.get(polling_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0)
        r.raise_for_status()
        j = r.json()
        status = j.get("status", "unknown")
        if status != last_status and on_progress:
            on_progress(status)
            last_status = status
        if status == "completed":
            url = (
                j.get("video_url")
                or j.get("url")
                or j.get("output_url")
                or (j.get("signed_urls") or [None])[0]
                or (j.get("unsigned_urls") or [None])[0]
            )
            if not url:
                videos = j.get("videos") or j.get("output", {}).get("videos") or []
                if videos and isinstance(videos, list):
                    url = videos[0].get("url") if isinstance(videos[0], dict) else videos[0]
            if not url:
                raise RuntimeError(f"Veo completed but no video URL: {json.dumps(j)[:500]}")
            return url
        if status == "failed":
            err = j.get("error") or j.get("message") or "unknown error"
            raise RuntimeError(f"Veo failed: {err}")
        time.sleep(10)
    raise TimeoutError(f"Veo polling timeout ({timeout_sec}s)")


def _download_video(url: str, output_path: Path) -> Path:
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    headers = {"Authorization": f"Bearer {api_key}"} if "openrouter.ai" in url else {}
    r = httpx.get(url, headers=headers, timeout=300.0)
    r.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(r.content)
    return output_path


def enhance_prompt(scene_description: str) -> str:
    """Tylko enhance prompt (preview bez wywoływania Veo)."""
    return _enhance_to_veo_prompt(scene_description)


def render_lego_video(
    final_prompt: str,
    format_key: str,
    duration: int = VEO_DEFAULT_DURATION,
    tier: str = VEO_DEFAULT_TIER,
    image_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> Path:
    """Render Veo z gotowym promptem. Tier = lite/fast/standard. image_path = optional first-frame ref."""
    if format_key not in VEO_FORMATS:
        raise ValueError(f"Nieznany format: {format_key}. Dostępne: {list(VEO_FORMATS.keys())}")
    if duration not in VEO_DURATIONS:
        raise ValueError(f"Veo wspiera duration: {VEO_DURATIONS}. Podano: {duration}")
    if tier not in VEO_TIERS:
        raise ValueError(f"Nieznany tier: {tier}. Dostępne: {list(VEO_TIERS.keys())}")

    fmt = VEO_FORMATS[format_key]
    if fmt["aspect_ratio"] not in VEO_TIERS[tier]["aspect_ratios"]:
        raise ValueError(
            f"Tier {tier} nie wspiera aspect ratio {fmt['aspect_ratio']}. "
            f"Obsługiwane: {VEO_TIERS[tier]['aspect_ratios']}"
        )

    if on_progress:
        on_progress(f"submitting_to_veo_{tier}")

    vid_id, polling_url = _veo_create(final_prompt, duration, fmt["aspect_ratio"], tier=tier,
                                       image_path=image_path)

    if on_progress:
        on_progress(f"submitted (id: {vid_id[:12]}...)")

    video_url = _veo_poll(polling_url, on_progress=on_progress)

    if on_progress:
        on_progress("downloading")

    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_videos"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = output_dir / f"lego_{tier}_{format_key}_{duration}s_{ts}.mp4"
    _download_video(video_url, out)

    if on_progress:
        on_progress("completed")
    return out


def generate_lego_video(
    scene_description: str,
    format_key: str = "shorts",
    duration: int = VEO_DEFAULT_DURATION,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> tuple[str, Path]:
    """End-to-end: polski opis sceny → enhanced EN prompt → Veo 3.1 → mp4.

    Zwraca (final_prompt, mp4_path).
    """
    if on_progress:
        on_progress("enhancing_prompt")
    final_prompt = _enhance_to_veo_prompt(scene_description)
    if on_progress:
        on_progress("prompt_ready")

    path = render_lego_video(final_prompt, format_key, duration, output_dir, on_progress)
    return final_prompt, path


def concat_videos(video_paths: list[Path], output_path: Path) -> Path:
    """ffmpeg concat – łączy listę mp4 w jeden plik.

    Wymaga zgodnych parametrów (codec, aspect ratio, resolution). Veo daje zgodne klipy
    przy tym samym aspect_ratio + resolution + duration, więc `-c copy` (bez re-encode) wystarcza.
    """
    import subprocess
    import tempfile

    if not video_paths:
        raise ValueError("Pusta lista wideo do concat")
    if len(video_paths) == 1:
        return video_paths[0]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in video_paths:
            f.write(f"file '{Path(p).resolve()}'\n")
        list_path = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            # Concat copy może zawieść jeśli timebase/codec się różnią – fallback z re-encode
            cmd_fallback = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                str(output_path),
            ]
            proc2 = subprocess.run(cmd_fallback, capture_output=True, text=True)
            if proc2.returncode != 0:
                raise RuntimeError(f"ffmpeg concat failed (both copy and re-encode): {proc2.stderr[-500:]}")
    finally:
        os.unlink(list_path)
    return output_path
