"""Generator filmów `/eleven` – Seedance 2.0 via fal.ai + ElevenLabs Riley voice overlay.

Tom wkleja scenariusz (timeline + lektor jak w `/reklama`). Pipeline:
  1. LLM (Sonnet 4.6) parsuje scenariusz na sceny.
  2. Dla każdej sceny: enhance prompt (photoreal documentary), Seedance 2.0 render.
  3. Voice-over: ElevenLabs Riley TTS, ffmpeg replace audio per scena.
  4. Concat wszystkich scen w finalne wideo.
  5. Optional Lyria 3 music underlay.

fal.ai endpoint:
- standard: POST https://queue.fal.run/bytedance/seedance-2.0/text-to-video
- fast:     POST https://queue.fal.run/bytedance/seedance-2.0/fast/text-to-video

Authentication: header `Authorization: Key {FAL_KEY}`.
Async via queue: response z `request_id`, status_url, response_url.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

import chainlit_audio as caud
import chainlit_reklama_gen as creklama  # reuse parser_scenario_via_llm + split logic
import chainlit_veo_gen as cveo  # reuse concat_videos

FAL_BASE = "https://queue.fal.run"

# Default Riley (en/multi, premade in ElevenLabs PRO library)
ELEVEN_DEFAULT_VOICE = os.environ.get("ELEVEN_DEFAULT_VOICE", "riley")

SEEDANCE_TIERS = {
    "standard": {
        "endpoint": "bytedance/seedance-2.0/text-to-video",
        "label": "Standard ($0,30/s, 720p natywne)",
        "price_per_sec": 0.3034,
        "resolution": "720p",
    },
    "fast": {
        "endpoint": "bytedance/seedance-2.0/fast/text-to-video",
        "label": "Fast ($0,24/s, 480p→720p upscale)",
        "price_per_sec": 0.2419,
        "resolution": "720p",
    },
}
SEEDANCE_DEFAULT_TIER = "standard"

SEEDANCE_ASPECT_RATIOS = {
    "21:9": {"label": "Cinema 21:9", "use_case": "Kino, banery web hero"},
    "16:9": {"label": "Pozioma 16:9", "use_case": "YouTube, prezentacje"},
    "4:3":  {"label": "Stara TV 4:3", "use_case": "Retro / archiwum styl"},
    "1:1":  {"label": "Kwadrat 1:1", "use_case": "IG feed, FB feed"},
    "3:4":  {"label": "Lekko pion 3:4", "use_case": "IG portrait"},
    "9:16": {"label": "Pion 9:16", "use_case": "Reels/Shorts/TikTok"},
}

SEEDANCE_MIN_DURATION = 4
SEEDANCE_MAX_DURATION = 15


def _enhance_seedance_prompt(image_desc: str) -> str:
    """LLM tworzy prompt EN dla Seedance 2.0 (photoreal documentary, no character dialog – Riley overlay osobno)."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_ELEVEN_PROMPT_MODEL", "anthropic/claude-sonnet-4.6")
    instr = f"""Stwórz cinematic prompt PO ANGIELSKU do modelu Seedance 2.0 (ByteDance text-to-video).

Opis sceny (po polsku, od użytkownika):
{image_desc}

WYMAGANIA:

1. STYL: Photorealistic documentary-style cinematography. Natural skin texture, lifelike motion, authentic expression.
2. SCENA: opis akcji, postaci (jeśli są), otoczenia, gestów.
3. CAMERA: konkretny shot type (medium / close-up / wide / dolly / handheld), depth of field.
4. LIGHTING: konkretny mood (soft natural daylight / warm side lighting / dramatic filmic).
5. AUDIO: WYŁĄCZNIE ambient sounds (typing, distant chatter, footsteps, office hum, etc.).
   ZAKAZ spoken dialogue od jakiejkolwiek postaci – voice-over Riley będzie dodany OSOBNO przez ElevenLabs.
6. LONG: 60-120 słów EN, jeden paragraf, jedna płynna proza.

ZAKAZ SŁÓW: "AI-generated", "stylized", "stock", "fictional", "rendered", "CGI", "animated".
ZAKAZ: konkretne numery telefonu, adresy URL, nazwy marek konkurencji.

Zwróć WYŁĄCZNIE finalny prompt EN, bez wstępu, komentarzy, cudzysłowów otaczających."""

    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Eleven Seedance Prompt",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": instr}],
            "temperature": 0.7,
            "max_tokens": 600,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _seedance_submit(prompt: str, aspect_ratio: str, duration: int, tier: str) -> dict:
    """POST do fal.ai. Zwraca dict z request_id, status_url, response_url."""
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        raise RuntimeError("FAL_KEY nie ustawiony w env. Dodaj klucz fal.ai do .mcp.json.")
    endpoint = SEEDANCE_TIERS[tier]["endpoint"]
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "duration": str(duration),  # fal.ai oczekuje string sekund
        "resolution": "720p",
        "generate_audio": False,  # voice-over przez ElevenLabs Riley, audio Seedance nie potrzebne
    }
    r = httpx.post(
        f"{FAL_BASE}/{endpoint}",
        headers={
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60.0,
    )
    if r.status_code not in (200, 202):
        raise RuntimeError(f"fal.ai submit {r.status_code}: {r.text[:500]}")
    return r.json()


def _seedance_poll(status_url: str, response_url: str, on_progress=None, timeout_sec: int = 1800) -> str:
    """Polling fal.ai aż status COMPLETED. Zwraca video URL."""
    fal_key = os.environ["FAL_KEY"]
    H = {"Authorization": f"Key {fal_key}"}
    start = time.time()
    last_status = None
    while time.time() - start < timeout_sec:
        r = httpx.get(status_url, headers=H, timeout=30.0)
        r.raise_for_status()
        j = r.json()
        status = j.get("status", "UNKNOWN")
        if status != last_status and on_progress:
            on_progress(status)
            last_status = status
        if status == "COMPLETED":
            # Pobierz pełen response
            r2 = httpx.get(response_url, headers=H, timeout=30.0)
            r2.raise_for_status()
            result = r2.json()
            # fal.ai zazwyczaj zwraca {"video": {"url": "..."}}
            video = result.get("video") or {}
            url = video.get("url") if isinstance(video, dict) else None
            if not url:
                # fallback shape
                url = result.get("video_url") or result.get("url")
            if not url:
                raise RuntimeError(f"fal.ai COMPLETED ale brak video URL: {json.dumps(result)[:500]}")
            return url
        if status in ("FAILED", "CANCELLED"):
            err = j.get("error") or j.get("message") or "unknown"
            raise RuntimeError(f"Seedance failed: {err}")
        time.sleep(10)
    raise TimeoutError(f"Seedance polling timeout ({timeout_sec}s)")


def _download_video(url: str, output_path: Path) -> Path:
    r = httpx.get(url, timeout=300.0)
    r.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(r.content)
    return output_path


def render_seedance_clip(
    prompt: str,
    aspect_ratio: str,
    duration: int,
    tier: str = SEEDANCE_DEFAULT_TIER,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> Path:
    """Render pojedynczy klip Seedance 2.0. Zwraca ścieżkę do mp4 (bez voice-over)."""
    import datetime

    if aspect_ratio not in SEEDANCE_ASPECT_RATIOS:
        raise ValueError(f"Nieznany aspect_ratio: {aspect_ratio}. Dostępne: {list(SEEDANCE_ASPECT_RATIOS)}")
    if not (SEEDANCE_MIN_DURATION <= duration <= SEEDANCE_MAX_DURATION):
        raise ValueError(f"Duration {duration}s poza zakresem {SEEDANCE_MIN_DURATION}-{SEEDANCE_MAX_DURATION}.")
    if tier not in SEEDANCE_TIERS:
        raise ValueError(f"Nieznany tier: {tier}. Dostępne: {list(SEEDANCE_TIERS)}")

    if on_progress:
        on_progress(f"seedance_submitting_{tier}")
    submission = _seedance_submit(prompt, aspect_ratio, duration, tier)
    status_url = submission["status_url"]
    response_url = submission["response_url"]
    request_id = submission.get("request_id", "?")
    if on_progress:
        on_progress(f"seedance_queued_{request_id[:12]}")

    video_url = _seedance_poll(status_url, response_url, on_progress=on_progress)
    if on_progress:
        on_progress("seedance_downloading")

    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_videos"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ar_safe = aspect_ratio.replace(":", "x")
    out = output_dir / f"eleven_{tier}_{ar_safe}_{duration}s_{ts}.mp4"
    _download_video(video_url, out)
    if on_progress:
        on_progress("seedance_completed")
    return out


def parse_scenario_via_llm(scenario_text: str) -> list[dict]:
    """Reuse parsera z chainlit_reklama_gen – ten sam format scenariusza."""
    return creklama.parse_scenario_via_llm(scenario_text)


def replace_audio_with_riley(
    video_path: Path | str,
    voiceover_text: str,
    speed: float = 1.0,
    output_dir: Path | str | None = None,
) -> Path:
    """ElevenLabs Riley TTS → ffmpeg replace audio. Zwraca voiced mp4."""
    import datetime
    import subprocess

    video_path = Path(video_path)
    output_dir = Path(output_dir) if output_dir else video_path.parent
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    audio_bytes = caud.tts_elevenlabs(voiceover_text, voice_key="riley", speed=speed)
    audio_tmp = output_dir / f"_riley_{ts}.mp3"
    audio_tmp.write_bytes(audio_bytes)

    final_path = output_dir / f"eleven_scene_{ts}_voiced.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_tmp),
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(final_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        if audio_tmp.exists():
            audio_tmp.unlink()
    except Exception:
        pass
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg replace audio: {proc.stderr[-500:]}")
    return final_path
