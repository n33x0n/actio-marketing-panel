"""Generator filmów dla Chainlit przez HeyGen API v2 + ElevenLabs (native integration).

Komenda `/film <temat>` w czacie → wybór awatara → głosu → formatu → generuje skrypt
przez LLM (Sonnet 4.6) → wysyła do HeyGen → poll status → pobiera MP4.

Łatwo dodać nowe awatary / głosy / formaty – wystarczy dopisać entry do dictów.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from pathlib import Path

import httpx

# ────────────────────────────────────────────────────────────────
# REGISTRY – łatwo rozszerzyć o kolejne awatary/głosy/formaty
# ────────────────────────────────────────────────────────────────

AVATARS = {
    "kasia": {
        "label": "Kaśka z Actio",
        "avatar_id": os.environ.get("HEYGEN_AVATAR_KASIA", "fa9ebdb33ed2458fba07db23a8d3e7b0"),
        "description": "Kobieca postać, biznesowo-luzackie podejście, polski głos",
    },
    # Dodanie nowego awatara: dopisać klucz tutaj. Plus dodaj env var HEYGEN_AVATAR_<NAZWA>.
    # "marek": {
    #     "label": "Marek z Actio",
    #     "avatar_id": os.environ.get("HEYGEN_AVATAR_MAREK", ""),
    #     "description": "...",
    # },
}

VOICES = {
    "olka": {
        "label": "Olka z Actio",
        "voice_id": os.environ.get("HEYGEN_VOICE_OLKA", "5f52008a2c5444ac8d9bca91fe815021"),
        "default_speed": 1.0,
        "description": "ElevenLabs Aleksandra (zaimportowana do HeyGen) – professional, ciepły",
    },
    "kaska": {
        "label": "Kaśka z Actio",
        "voice_id": os.environ.get("HEYGEN_VOICE_KASKA", "9177d977f97d4783a014f919f00e7969"),
        "default_speed": 1.4,
        "description": "ElevenLabs Maria - Quiet and Gentle (zaimportowana) – energiczny ekspercki (1.4× speed)",
    },
    "marta": {
        "label": "Marta z Actio",
        "voice_id": os.environ.get("HEYGEN_VOICE_MARTA", "23cadfe1fa204dffbb1fae400764c85a"),
        "default_speed": 1.0,
        "description": "ElevenLabs Marta - Calm, Sympathetic (zaimportowana) – empatyczny doradczy",
    },
}

VIDEO_FORMATS = {
    "shorts": {
        "label": "Pion 9:16",
        "width": 720,
        "height": 1280,
        "aspect": "9:16",
        "use_case": "TikTok, IG Reels, FB Reels, YouTube Shorts, Stories",
    },
    "youtube": {
        "label": "Poziom 16:9",
        "width": 1280,
        "height": 720,
        "aspect": "16:9",
        "use_case": "YouTube, LinkedIn embed, prezentacje",
    },
    "square": {
        "label": "Kwadrat 1:1",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "use_case": "Instagram feed, Facebook feed, LinkedIn post",
    },
}

DEFAULT_DURATION_SEC = 90
WORDS_PER_MIN_PL = 145  # tempo mowy polskiej


# ────────────────────────────────────────────────────────────────
# SCRIPT GENERATION via OpenRouter (Sonnet 4.6)
# ────────────────────────────────────────────────────────────────

def _generate_script(topic: str, duration_sec: int = DEFAULT_DURATION_SEC) -> str:
    """LLM generuje skrypt polski na zadany temat + długość. Zoptymalizowane dla lip-sync."""
    target_words = int(duration_sec / 60 * WORDS_PER_MIN_PL)
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_VIDEO_SCRIPT_MODEL", "anthropic/claude-sonnet-4.6")

    prompt = f"""Jesteś content marketerem Actio (polski operator VoIP B2B, marka SYNTELL S.A.).

Napisz krótki skrypt do filmu video z awatarem AI na temat: "{topic}"

WYMAGANIA:
- Długość: dokładnie {target_words} słów (±10) — film będzie miał {duration_sec} sekund
- Język: polski, ton zaopiekowujący-ekspercki (nie korpomowy, nie zbyt luzacki)
- Krótkie zdania (max 12-15 słów na zdanie) — dla lepszego lip-sync awatara
- Bez emoji, bez markdownu, bez znaków specjalnych — tylko czysty tekst do mówienia
- Struktura: hook (3-5 sek) → problem (15-20 sek) → rozwiązanie Actio (40-50 sek) → CTA (10-15 sek)
- Na końcu wyraźny CTA, np. "Sprawdź ofertę na actio.pl lub zadzwoń"
- Słowo "Actio" wymawiaj jak naturalnie się czyta, nie literuj
- Nie używaj liczb z rozszerzeniami (np. "100 procent" zamiast "100%")

Zwróć WYŁĄCZNIE czysty skrypt — bez wstępu, bez komentarzy, bez cudzysłowów na końcu. Sam tekst do wypowiedzenia."""

    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Chainlit Video",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1500,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ────────────────────────────────────────────────────────────────
# HEYGEN API v2
# ────────────────────────────────────────────────────────────────

_HEYGEN_BASE = "https://api.heygen.com"


def _heygen_headers() -> dict:
    return {
        "X-Api-Key": os.environ["HEYGEN_API_KEY"],
        "Content-Type": "application/json",
    }


def _heygen_create_video(avatar_id: str, voice_id: str, script: str, width: int, height: int, speed: float = 1.0) -> str:
    """POST /v2/video/generate – zwraca video_id (do pollingu).

    Avatar Kasia to Photo Avatar (talking_photo), nie standard Avatar – stąd type='talking_photo'.
    speed: tempo mowy 0.5-2.0 (UI HeyGen slider 1.4× = API 1.4).
    """
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "talking_photo",
                    "talking_photo_id": avatar_id,
                    "scale": 1.0,
                    "talking_photo_style": "square",
                    "talking_style": "expressive",
                    "expression": "default",
                    "super_resolution": True,
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": voice_id,
                    "speed": float(speed),
                },
                "background": {
                    "type": "color",
                    "value": "#fafbfc",
                },
            }
        ],
        "dimension": {
            "width": width,
            "height": height,
        },
    }
    r = httpx.post(
        f"{_HEYGEN_BASE}/v2/video/generate",
        headers=_heygen_headers(),
        json=payload,
        timeout=60.0,
    )
    if r.status_code != 200:
        # Capture exact error message from HeyGen for debugging
        try:
            err_body = r.json()
        except Exception:
            err_body = r.text
        raise RuntimeError(
            f"HeyGen {r.status_code}: {json.dumps(err_body, ensure_ascii=False)} | "
            f"payload sent: {json.dumps(payload, ensure_ascii=False)[:500]}"
        )
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"HeyGen error: {data['error']}")
    return data["data"]["video_id"]


def _heygen_poll_status(video_id: str) -> dict:
    """GET /v1/video_status.get – zwraca {status, video_url, ...}."""
    r = httpx.get(
        f"{_HEYGEN_BASE}/v1/video_status.get",
        headers=_heygen_headers(),
        params={"video_id": video_id},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json().get("data", {})


def _heygen_wait_for_completion(video_id: str, on_progress=None, timeout_sec: int = 900) -> str:
    """Polling co 30 sek aż video się wyrenderuje. Zwraca video_url. Callback on_progress(status_str)."""
    start = time.time()
    last_status = None
    while time.time() - start < timeout_sec:
        info = _heygen_poll_status(video_id)
        status = info.get("status", "unknown")
        if status != last_status and on_progress:
            on_progress(status)
            last_status = status
        if status == "completed":
            return info["video_url"]
        if status == "failed":
            err = info.get("error", "unknown error")
            raise RuntimeError(f"HeyGen video failed: {err}")
        time.sleep(30)
    raise TimeoutError(f"HeyGen polling timeout ({timeout_sec}s)")


def _download_video(url: str, output_path: Path) -> Path:
    """Pobierz mp4 z HeyGen CDN."""
    r = httpx.get(url, timeout=300.0)
    r.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(r.content)
    return output_path


# ────────────────────────────────────────────────────────────────
# PUBLIC API
# ────────────────────────────────────────────────────────────────

def generate_script(topic: str, duration_sec: int = DEFAULT_DURATION_SEC) -> str:
    """Wygeneruj skrypt do filmu (1 step, łatwy do preview przed renderem)."""
    return _generate_script(topic, duration_sec)


def render_video(
    script: str,
    avatar_key: str,
    voice_key: str,
    format_key: str,
    speed: float | None = None,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> Path:
    """Wyrender wideo HeyGen + zapisz lokalnie. Zwraca ścieżkę do mp4.

    speed: jeśli None, używa default_speed z VOICES dict (Kaśka=1.4, reszta=1.0).
    """
    if avatar_key not in AVATARS:
        raise ValueError(f"Nieznany awatar: {avatar_key}. Dostępne: {list(AVATARS.keys())}")
    if voice_key not in VOICES:
        raise ValueError(f"Nieznany głos: {voice_key}. Dostępne: {list(VOICES.keys())}")
    if format_key not in VIDEO_FORMATS:
        raise ValueError(f"Nieznany format: {format_key}. Dostępne: {list(VIDEO_FORMATS.keys())}")

    avatar = AVATARS[avatar_key]
    voice = VOICES[voice_key]
    fmt = VIDEO_FORMATS[format_key]
    actual_speed = speed if speed is not None else voice.get("default_speed", 1.0)

    if on_progress:
        on_progress("submitting")

    video_id = _heygen_create_video(
        avatar_id=avatar["avatar_id"],
        voice_id=voice["voice_id"],
        script=script,
        width=fmt["width"],
        height=fmt["height"],
        speed=actual_speed,
    )

    if on_progress:
        on_progress(f"submitted (video_id: {video_id[:12]}...)")

    video_url = _heygen_wait_for_completion(video_id, on_progress=on_progress)

    if on_progress:
        on_progress("downloading")

    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_videos"
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = output_dir / f"{avatar_key}_{voice_key}_{format_key}_{ts}.mp4"
    _download_video(video_url, out)

    if on_progress:
        on_progress("completed")

    return out


def generate_video(topic: str, avatar_key: str, voice_key: str, format_key: str,
                   duration_sec: int = DEFAULT_DURATION_SEC,
                   output_dir: Path | str | None = None,
                   on_progress=None) -> tuple[str, Path]:
    """End-to-end: temat → skrypt → render → mp4. Zwraca (script, mp4_path)."""
    if on_progress:
        on_progress("generating_script")
    script = _generate_script(topic, duration_sec)
    if on_progress:
        on_progress("script_ready")
    path = render_video(script, avatar_key, voice_key, format_key, output_dir, on_progress)
    return script, path
