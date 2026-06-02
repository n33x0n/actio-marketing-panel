"""Generator strukturalnych reklam (B-roll + voice-over) przez Veo 3.1 + ElevenLabs.

Komenda `/reklama` w czacie – Tom wkleja scenariusz w dowolnym formacie (timeline + lektor).
LLM (Sonnet 4.6) parsuje na strukturalne sceny → JSON. Następnie:
  1. Dla każdej sceny generuje Veo prompt B-roll (BEZ dialog) z personą Kasi
  2. Auto-split scen >8 s na chunki Veo (4/6/8 s) → render + ffmpeg concat per scena
  3. ElevenLabs Maria TTS z tekstu lektora → ffmpeg replace audio per scena
  4. Concat wszystkich scen → final mp4
  5. Optional Lyria 3 music underlay

Wsparcie: scenariusze 30-90 s, voice-over poza kadrem, multi-scene narrative.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

import chainlit_audio as caud
import chainlit_veo_gen as cveo

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

REKLAMA_DEFAULT_VOICE = os.environ.get("REKLAMA_DEFAULT_VOICE", "kaska")  # ElevenLabs Maria


def parse_scenario_via_llm(scenario_text: str) -> list[dict]:
    """LLM parsuje wklejony scenariusz (dowolny format) na strukturalne sceny."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_REKLAMA_PARSER_MODEL", "anthropic/claude-sonnet-4.6")

    instr = f"""Jesteś parsing assistantem. Sparsuj wklejony scenariusz reklamy wideo na sceny.

Wejście (dowolny format – timeline, tabela, markdown, plaintext):
\"\"\"
{scenario_text}
\"\"\"

Zwróć JSON object: {{"scenes": [...]}}.
Każdy element listy:
{{
  "duration_s": <int – długość sceny w sekundach>,
  "image": <string – opis obrazu/akcji w scenie, PO POLSKU>,
  "voiceover": <string – dokładny tekst lektora który ma być wypowiedziany w tej scenie, PO POLSKU>
}}

Wskazówki:
- Timestamp `0:00-0:12` lub `[0:00-0:12]` → duration_s = 12 (różnica end-start, w sekundach)
- Timestamp `0:12-0:22` → duration_s = 10 (różnica)
- Timestamp `0:22-0:35` → duration_s = 13
- Timestamp `0:35-0:48` → duration_s = 13
- Timestamp `0:48-1:00` → duration_s = 12 (1:00 = 60 sek)
- `[12s]` lub `12 sek` lub `Czas: 12s` → duration_s = 12
- **NIGDY** nie ustawiaj duration_s = 8 jako default – ZAWSZE oblicz z timestampów / explicit duration
- Jeśli brak duration → zakładaj 8s

- "Lektor:" / "LEKTOR:" / "Narrator:" / "Voice-over:" → voiceover field
- "Obraz:" / "Video:" lub blok przed Lektor → image field
- IGNORUJ nagłówki/tytuły, tylko sceny
- Voiceover = dokładny tekst do wypowiedzenia (BEZ "Lektor mówi:", BEZ stage directions)

**WAŻNE – content filter Veo bezpieczeństwo dla image field**:
- USUŃ z image: konkretne numery telefonów (np. "+48 61 648..."), konkretne URL-e (np. "www.actio.pl"), nazwy marek konkurencji
- ZACHOWAJ w voiceover dosłownie – TTS to mówi, bez problemu
- W image opis "logo ACTIO" zmień na "logo of the company", "numer telefonu" → "phone number on screen", "www.actio.pl" → "website URL"

Zwróć WYŁĄCZNIE czysty JSON object, bez markdown code fence."""

    r = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Reklama Parser",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": instr}],
            "temperature": 0.2,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
        },
        timeout=90.0,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    parsed = json.loads(content)
    scenes = parsed.get("scenes") or parsed.get("data") or []
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError(f"LLM nie zwrócił listy scen. Surowa odpowiedź: {content[:300]}")
    # Validate
    for i, s in enumerate(scenes, 1):
        if not all(k in s for k in ("duration_s", "image", "voiceover")):
            raise RuntimeError(f"Scena {i} brak wymaganych pól: {list(s.keys())}")
    return scenes


def split_to_veo_chunks(target_s: int) -> list[int]:
    """Zwraca listę długości chunków Veo (4/6/8s) sumujących się do co najmniej target_s.

    Mapowanie zoptymalizowane na minimum klipów (mniej generations = mniej $$).
    Veo wspiera tylko 4, 6, 8 sek. Dla większych długości łączymy w chunki.
    """
    if target_s <= 4:
        return [4]
    if target_s <= 6:
        return [6]
    if target_s <= 8:
        return [8]
    if target_s <= 10:
        return [4, 6]
    if target_s <= 12:
        return [6, 6]
    if target_s <= 14:
        return [6, 8]
    if target_s <= 16:
        return [8, 8]
    if target_s <= 20:
        return [4, 8, 8]
    if target_s <= 22:
        return [6, 8, 8]
    if target_s <= 24:
        return [8, 8, 8]
    # >24s – greedy 8s chunks z resztą
    chunks = []
    remaining = target_s
    while remaining > 8:
        chunks.append(8)
        remaining -= 8
    if remaining > 0:
        chunks.append(4 if remaining <= 4 else 6 if remaining <= 6 else 8)
    return chunks


def _enhance_broll_prompt(image_desc: str) -> str:
    """LLM tworzy Veo prompt dla B-roll (NO character dialog – voice-over osobno przez ElevenLabs)."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_REKLAMA_PROMPT_MODEL", "anthropic/claude-sonnet-4.6")

    instr = f"""Stwórz cinematic prompt PO ANGIELSKU do modelu Veo 3.1 dla sceny B-roll.

Opis sceny (po polsku, od użytkownika):
{image_desc}

WYMAGANIA OBOWIĄZKOWE:

1. STYL: Photorealistic documentary-style cinematography. Natural skin texture, lifelike expressions, lifelike motion.
2. PERSONA (jeśli scena pokazuje osoby): zaufana młoda business presenter, navy blazer + white shirt,
   modern office environment z brick wall accents, natural daylight z dużych okien.
3. AUDIO: WYŁĄCZNIE ambient sounds (typing, distant office chatter, soft background hum, footsteps).
   ZAKAZ spoken dialogue od jakiejkolwiek postaci – voice-over będzie dodany OSOBNO.
4. CAMERA: konkretny shot type (medium / close-up / wide / dolly / handheld).
5. LIGHTING: konkretny mood (soft natural daylight / warm side lighting / dramatic filmic).
6. LONG: 60-100 słów EN, jeden paragraf, jedna płynna proza.

ZAKAZ SŁÓW: "AI-generated", "stylized", "stock", "fictional", "rendered", "CGI", "animated",
imię "Kasia", konkretny wiek/narodowość/kolor oczu, marki konkurencji.

Zwróć WYŁĄCZNIE finalny prompt EN, bez wstępu, komentarzy, cudzysłowów otaczających."""

    r = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Reklama Broll Prompt",
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


def replace_audio_with_voiceover(
    video_path: Path | str,
    voiceover_text: str,
    voice_key: str = REKLAMA_DEFAULT_VOICE,
    speed: float = 1.0,
    output_dir: Path | str | None = None,
) -> Path:
    """ElevenLabs TTS → ffmpeg replace audio track. Zwraca ścieżkę do voiced mp4."""
    import datetime
    import subprocess

    video_path = Path(video_path)
    output_dir = Path(output_dir) if output_dir else video_path.parent
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    audio_bytes = caud.tts_elevenlabs(voiceover_text, voice_key=voice_key, speed=speed)
    audio_tmp = output_dir / f"_voiceover_{ts}.mp3"
    audio_tmp.write_bytes(audio_bytes)

    final_path = output_dir / f"reklama_scene_{ts}_voiced.mp4"
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


def enhance_broll_prompt(image_desc: str) -> str:
    """Public wrapper around _enhance_broll_prompt (potrzebne dla app.py orchestration)."""
    return _enhance_broll_prompt(image_desc)


def render_voiceover_scene(
    scene: dict,
    format_key: str,
    tier: str,
    voice_key: str = REKLAMA_DEFAULT_VOICE,
    speed: float = 1.0,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> tuple[Path, dict]:
    """Render pojedyncza scena z voice-overem: multi-chunk Veo (B-roll) + ElevenLabs TTS overlay.

    Zwraca (final_mp4, info_dict z metadata: chunks, veo_prompt, voiceover, voiceover_path).
    """
    import datetime
    import subprocess

    duration_s = int(scene["duration_s"])
    chunks = split_to_veo_chunks(duration_s)
    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if on_progress:
        on_progress(f"enhancing_broll_prompt_({len(chunks)}chunks)")
    veo_prompt = _enhance_broll_prompt(scene["image"])

    # Render N chunków Veo (sekwencyjnie – polling)
    chunk_paths: list[Path] = []
    for i, chunk_dur in enumerate(chunks, 1):
        if on_progress:
            on_progress(f"rendering_veo_chunk_{i}/{len(chunks)}_{chunk_dur}s")
        p = cveo.render_lego_video(
            final_prompt=veo_prompt,
            format_key=format_key,
            duration=chunk_dur,
            tier=tier,
            output_dir=output_dir,
        )
        chunk_paths.append(p)

    # Concat chunków (jeśli >1)
    if len(chunk_paths) > 1:
        if on_progress:
            on_progress("concat_chunks")
        scene_video = output_dir / f"reklama_scene_{ts}_concat.mp4"
        cveo.concat_videos(chunk_paths, scene_video)
    else:
        scene_video = chunk_paths[0]

    # Generuj voice-over przez ElevenLabs Maria
    if on_progress:
        on_progress(f"generating_voiceover_elevenlabs_speed{speed}")
    audio_bytes = caud.tts_elevenlabs(scene["voiceover"], voice_key=voice_key, speed=speed)
    audio_path = output_dir / f"reklama_voiceover_{ts}.mp3"
    audio_path.write_bytes(audio_bytes)

    # Replace audio: zostawić wideo, użyć TTS jako track audio. -shortest dopasuje do krótszego.
    # Jeśli TTS dłuższy niż wideo – zostanie ucięty. Jeśli krótszy – wideo trwa dłużej (cisza na końcu).
    if on_progress:
        on_progress("replacing_audio_track")
    final_path = output_dir / f"reklama_scene_{ts}_voiced.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(scene_video),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(final_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg replace audio: {proc.stderr[-500:]}")

    # Cleanup intermediate
    if audio_path.exists():
        audio_path.unlink()

    info = {
        "duration_s": duration_s,
        "chunks": chunks,
        "veo_prompt": veo_prompt,
        "voiceover": scene["voiceover"],
        "chunk_count": len(chunks),
    }
    return final_path, info


def render_full_reklama(
    scenes: list[dict],
    format_key: str,
    tier: str = "lite",  # /reklama hardcodowane Lite (Tom preference)
    voice_key: str = REKLAMA_DEFAULT_VOICE,
    speed: float = 1.0,
    with_music: bool = False,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> tuple[Path, dict]:
    """Render kompletna reklama: N scen × multi-chunk + voice-over + concat + optional music.

    Zwraca (final_mp4, metadata).
    """
    import datetime

    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "chainlit_videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    scene_paths: list[Path] = []
    scenes_info: list[dict] = []
    for i, scene in enumerate(scenes, 1):
        if on_progress:
            on_progress(f"scene_{i}/{len(scenes)}_starting")
        p, info = render_voiceover_scene(
            scene=scene,
            format_key=format_key,
            tier=tier,
            voice_key=voice_key,
            speed=speed,
            output_dir=output_dir,
            on_progress=on_progress,
        )
        scene_paths.append(p)
        scenes_info.append(info)

    # Concat wszystkich scen
    if len(scene_paths) > 1:
        if on_progress:
            on_progress("concat_all_scenes")
        final_path = output_dir / f"reklama_{tier}_{format_key}_{ts}.mp4"
        cveo.concat_videos(scene_paths, final_path)
    else:
        final_path = scene_paths[0]

    # Optional music
    if with_music:
        if on_progress:
            on_progress("adding_lyria_music")
        full_voiceover = " ".join(s["voiceover"] for s in scenes)
        try:
            final_path, _music_info = caud.add_music_to_video(
                video_path=final_path,
                scene_or_script=full_voiceover,
                output_dir=output_dir,
            )
        except Exception:
            # Music fail nie blokuje całości – return without music
            pass

    metadata = {
        "scene_count": len(scenes),
        "total_duration_s": sum(s["duration_s"] for s in scenes),
        "scenes_info": scenes_info,
        "tier": tier,
        "format_key": format_key,
        "with_music": with_music,
    }
    return final_path, metadata
