"""Audio utilities dla Chainlit – ElevenLabs TTS + ffmpeg overlay na wideo.

Komenda `/tekst <głos> <text>` w czacie bierze ostatni wygenerowany film z sesji
(z /lego, /scenariusz, /dialog) i zastępuje ścieżkę audio nową syntezą TTS.

ElevenLabs PRO: 610k chars/m, model eleven_multilingual_v2 świetnie radzi sobie z PL.
"""
from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

import httpx

EL_API_BASE = "https://api.elevenlabs.io/v1"
EL_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
LYRIA_MODEL = "google/lyria-3-clip-preview"  # 30 sek, $0.04 per clip
LYRIA_PRO_MODEL = "google/lyria-3-pro-preview"  # full-length, $0.08
MUSIC_DUCK_VOLUME = float(os.environ.get("MUSIC_DUCK_VOLUME", "0.18"))  # 0.0-1.0, default 18% pod voice

VOICES_EL = {
    "olka": {
        "label": "Olka (Aleksandra)",
        "voice_id_env": "ELEVENLABS_VOICE_OLKA",
        "voice_id_default": "NOWYzprzTwfZQqU76pBX",
        "description": "Conversational, professional",
    },
    "kaska": {
        "label": "Kaśka (Maria - Quiet & Gentle)",
        "voice_id_env": "ELEVENLABS_VOICE_KASKA",
        "voice_id_default": "d4Z5Fvjohw3zxGpV8XUV",
        "description": "Narrative, calm",
    },
    "marta": {
        "label": "Marta (Calm & Empathetic)",
        "voice_id_env": "ELEVENLABS_VOICE_MARTA",
        "voice_id_default": "lehrjHysCyPSvjt0uSy6",
        "description": "Advertisement, classy",
    },
    "riley": {
        "label": "Riley (Engaging Young Female, EN/multi)",
        "voice_id_env": "ELEVENLABS_VOICE_RILEY",
        "voice_id_default": "hA4zGnmTwX2NQiTRMt7o",
        "description": "ElevenLabs premade – American accent, multilingual",
    },
}


def _voice_id(voice_key: str) -> str:
    cfg = VOICES_EL[voice_key]
    return os.environ.get(cfg["voice_id_env"], cfg["voice_id_default"])


def tts_elevenlabs(text: str, voice_key: str = "kaska", speed: float = 1.0) -> bytes:
    """Syntezuje mp3 z tekstu przez ElevenLabs. speed = tempo mowy (0.7-1.2 zalecane).

    ElevenLabs API: voice_settings.speed (range 0.25-4.0, default 1.0).
    Praktycznie poza 0.7-1.2 brzmi nienaturalnie. <0.7 = "spowolnione nagranie",
    >1.2 = "przyspieszone slo-mo".
    """
    if voice_key not in VOICES_EL:
        raise ValueError(f"Nieznany głos: {voice_key}. Dostępne: {list(VOICES_EL.keys())}")
    api_key = os.environ["ELEVENLABS_API_KEY"]
    voice_id = _voice_id(voice_key)

    speed_clamped = max(0.7, min(1.2, float(speed)))
    r = httpx.post(
        f"{EL_API_BASE}/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": EL_MODEL,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": speed_clamped,
            },
        },
        timeout=180.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs TTS {r.status_code}: {r.text[:300]}")
    return r.content


def _replace_audio_track(video_path: Path, new_audio_path: Path, output_path: Path) -> Path:
    """ffmpeg: zachowuje wideo, zastępuje ścieżkę audio. -shortest = ucina do krótszego."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(new_audio_path),
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg replace audio failed: {proc.stderr[-500:]}")
    return output_path


def overlay_voice_on_video(
    video_path: Path | str,
    text: str,
    voice_key: str = "kaska",
    speed: float = 1.0,
    output_dir: Path | str | None = None,
) -> tuple[Path, dict]:
    """End-to-end: TTS dla tekstu → zastępuje ścieżkę audio w mp4.

    Zwraca (output_mp4_path, info) gdzie info zawiera char_count, duration_audio_s itp.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Brak pliku wideo: {video_path}")
    output_dir = Path(output_dir) if output_dir else video_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_bytes = tts_elevenlabs(text, voice_key, speed=speed)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    audio_tmp = output_dir / f"_tts_{voice_key}_{ts}.mp3"
    audio_tmp.write_bytes(audio_bytes)

    output = output_dir / f"{video_path.stem}_voiced_{voice_key}_{ts}.mp4"
    try:
        _replace_audio_track(video_path, audio_tmp, output)
    finally:
        if audio_tmp.exists():
            audio_tmp.unlink()

    info = {
        "char_count": len(text),
        "voice_label": VOICES_EL[voice_key]["label"],
        "audio_bytes": len(audio_bytes),
    }
    return output, info


# ────────────────────────────────────────────────────────────────
# MUSIC GENERATION – Google Lyria 3 Clip via OpenRouter
# ────────────────────────────────────────────────────────────────

def _build_music_prompt(scene_or_script: str) -> str:
    """LLM (Sonnet 4.6) buduje ~50-word Lyria prompt na bazie scenariusza/skryptu.

    Lyria reaguje na prompt-y opisujące instrumenty, tempo, mood, gatunek. Bez wokalu (kolidowałby z TTS).
    """
    import httpx  # noqa: F401 (local re-import dla pewności gdy moduł cache'owany)
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_MUSIC_PROMPT_MODEL", "anthropic/claude-sonnet-4.6")

    instr = f"""Jesteś music supervisorem dobierającym tło dźwiękowe pod video Actio (operator VoIP B2B, marka SYNTELL).

Treść / scena do podłożenia:
{scene_or_script}

Zadanie: napisz krótki PROMPT po angielsku (40-70 słów) do Google Lyria 3 (text-to-music). Wymagania:

1. ZAWSZE: "no vocals, no lyrics, no spoken word, no drums, no percussion" – muzyka będzie podkładem pod istniejący voice-over.
2. INSTRUMENTACJA: dominuje piano + opcjonalnie ambient strings/pads. Lekkie, niezbyt jazzowe.
3. MOOD dobrany do treści: corporate-uplifting / calm-trust / playful-quirky / dramatic-build / tech-modern / warm-emotional. Wybierz JEDEN mood pasujący.
4. TEMPO: określ BPM (60-100 dla calm/corporate, 100-130 dla playful/upbeat).
5. STYLE: "minimalist", "cinematic background", "professional brand music", "subtle and supportive".
6. Bez znaków marek, bez konkretnych artystów.

Zwróć WYŁĄCZNIE finalny prompt po angielsku, bez wstępu, komentarzy, cudzysłowów otaczających."""

    r = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Lyria Music Prompt",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": instr}],
            "temperature": 0.7,
            "max_tokens": 300,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def generate_music_lyria(music_prompt: str) -> bytes:
    """Generuje 30-sek MP3 przez Lyria 3 Clip. Zwraca raw mp3 bytes."""
    import base64
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    payload = {
        "model": LYRIA_MODEL,
        "messages": [{"role": "user", "content": music_prompt}],
        "modalities": ["audio"],
        "stream": True,
    }
    audio_b64_chunks: list[str] = []
    with httpx.stream(
        "POST",
        f"{OPENROUTER_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180.0,
    ) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Lyria {r.status_code}: {r.read().decode()[:500]}")
        import json as _json
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:]
            if chunk == "[DONE]":
                break
            try:
                j = _json.loads(chunk)
                for choice in j.get("choices", []):
                    audio_part = choice.get("delta", {}).get("audio")
                    if audio_part and "data" in audio_part:
                        audio_b64_chunks.append(audio_part["data"])
            except _json.JSONDecodeError:
                pass
    if not audio_b64_chunks:
        raise RuntimeError("Lyria: brak audio w streamie")
    return base64.b64decode("".join(audio_b64_chunks))


def _mix_voice_and_music(video_path: Path, music_path: Path, output_path: Path,
                         music_volume: float = MUSIC_DUCK_VOLUME) -> Path:
    """ffmpeg: voice (1.0) + ducked music (~0.18), -shortest do długości wideo."""
    filter_complex = (
        f"[1:a]volume={music_volume}[mus];"
        f"[0:a][mus]amix=inputs=2:duration=first:normalize=0[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mix failed: {proc.stderr[-500:]}")
    return output_path


def add_music_to_video(
    video_path: Path | str,
    scene_or_script: str,
    output_dir: Path | str | None = None,
    music_volume: float = MUSIC_DUCK_VOLUME,
) -> tuple[Path, dict]:
    """End-to-end: LLM music prompt → Lyria gen → ffmpeg duck mix. Zwraca (output_mp4, info)."""
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Brak pliku wideo: {video_path}")
    output_dir = Path(output_dir) if output_dir else video_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    music_prompt = _build_music_prompt(scene_or_script)
    music_bytes = generate_music_lyria(music_prompt)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    music_tmp = output_dir / f"_lyria_{ts}.mp3"
    music_tmp.write_bytes(music_bytes)

    output = output_dir / f"{video_path.stem}_music_{ts}.mp4"
    try:
        _mix_voice_and_music(video_path, music_tmp, output, music_volume=music_volume)
    finally:
        if music_tmp.exists():
            music_tmp.unlink()

    info = {
        "music_prompt": music_prompt,
        "music_bytes": len(music_bytes),
        "music_volume": music_volume,
        "cost_usd": 0.04,
    }
    return output, info
