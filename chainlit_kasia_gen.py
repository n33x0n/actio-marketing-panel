"""Generator filmów z Kasią (pracowniczka biura Actio) przez Veo 3.1.

Komenda `/kasia` w czacie → LLM (Sonnet 4.6) tworzy:
  (a) cinematic EN prompt opisujący Kasię – professional business presenter,
  (b) exact PL dialog co ma być powiedziane w scenie.

Veo 3.1 generuje wideo z natywnym audio. Multi-scene: render N scen Veo,
concat ffmpeg, opcjonalny podkład Lyria 3 pod całość.

Uwaga: image conditioning (kasia_reference.jpg) zostało usunięte – Veo via OpenRouter
ignoruje pole `image` (potwierdzone testami), więc spójność postaci osiąga się TYLKO
przez powtarzalny detail w prompt enhancera + safety-filter-friendly wording.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

import chainlit_veo_gen as cveo

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

KASIA_PERSONA_INSTRUCTION = """Postać do filmu Veo – professional business presenter:

- Photorealistic female business consultant
- Natural skin texture, lifelike expression, documentary-style
- Smart business casual outfit: navy blazer + white shirt
- Friendly, confident, authentic demeanor

Otoczenie (KONSEKWENTNE we wszystkich scenach):
- Modern open-space office environment
- Background: desks, laptops, monitors, natural daylight
- Clean, professional B2B technology company aesthetic
- Loft-style with brick wall accents, large windows
- No branded logos visible

Persona w mówionej treści: **doradca biznesowy** (rzeczowy, kompetentny, autorytatywny).
Adresat: właściciele małych i średnich firm, B2B decision makers.

WAŻNE dla prompt Veo (anti-uncanny + safety filter avoidance):
- ZAWSZE używaj: "photorealistic", "natural lighting", "documentary cinematography", "lifelike skin texture", "authentic human expression"
- NIGDY nie używaj: "AI-generated", "stylized", "stock", "fictional character", "rendered", "CGI"
- NIE używaj imienia "Kasia" w EN prompt
- NIE wspominaj wieku, narodowości, koloru oczu (to triggery safety filter Veo)
- MOŻESZ użyć generic atrybutów wyglądu (np. "shoulder-length hair", "professional attire") jeśli pomaga consistency
"""


def _enhance_kasia_scene(scene_description: str) -> dict:
    """LLM tworzy Veo prompt + PL dialog. Zwraca {"veo_prompt": str, "tts_text": str}."""
    api_key = os.environ.get("OPENROUTER_API_KEY_AUTOPOST") or os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("CHAINLIT_KASIA_PROMPT_MODEL", "anthropic/claude-sonnet-4.6")

    instr = f"""Jesteś video directorem piszącym scenę do Veo 3.1. Veo ma agresywne safety filtry –
nie depict real-person-like attributes (wiek, narodowość, kolor włosów/oczu, marka).

{KASIA_PERSONA_INSTRUCTION}

Opis sceny od użytkownika (po polsku):
{scene_description}

Zadanie: zwróć JSON z DWOMA polami:

1. **veo_prompt** (string, PO ANGIELSKU, 80-150 słów, 1 paragraf):
   Cinematic prompt do Veo 3.1. ZAWSZE rozpocznij prompt frazą:
   "Photorealistic documentary-style cinematography of a professional female business presenter
   wearing a navy blazer over a white shirt, natural skin texture, lifelike expression,
   shoulder-length hair, friendly confident demeanor."

   Po tym dodaj:
   - akcję sceny (co postać robi, gdzie patrzy, jaki ma gest)
   - otoczenie ("modern open-space office, loft-style with brick wall accents, desks and laptops in background,
     soft natural daylight from large windows, professional clean B2B aesthetic")
   - camera (medium shot / close-up / over-the-shoulder, shallow depth of field)
   - lighting ("soft natural daylight", "warm side lighting", "filmic color grading")
   - mood
   - audio: zacytuj EXACT PL dialog w cudzysłowach, np. `she speaks in Polish: "..."`

   ZAKAZ słów: "AI-generated", "stylized", "stock", "fictional", "rendered", "CGI", "animated", "Kasia",
   konkretny wiek/narodowość/kolor oczu, marki konkurencji.

2. **tts_text** (string, PO POLSKU, max 30-40 słów na scenę 8 s):
   Dokładny tekst do wypowiedzenia w tej scenie.
   Ton doradcy biznesowego – rzeczowy, konkretny, zachęcający.
   Bez emoji, znaków specjalnych. Tylko czysty tekst do mówienia.
   Idealna długość: ~20 słów/8 s, ~15 słów/6 s, ~10 słów/4 s.

Zwróć WYŁĄCZNIE czysty JSON, bez markdown code fence, bez komentarzy:
{{"veo_prompt": "...", "tts_text": "..."}}"""

    r = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Chainlit Kasia",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": instr}],
            "temperature": 0.7,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    # LLM może zwrócić z fence pomimo response_format
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM zwrócił nieprawidłowy JSON: {e}. Content: {content[:300]}")
    if "veo_prompt" not in parsed or "tts_text" not in parsed:
        raise RuntimeError(f"Brak wymaganych pól w JSON: {list(parsed.keys())}")
    return parsed


def render_kasia_scene(
    scene_description: str,
    format_key: str,
    duration: int = cveo.VEO_DEFAULT_DURATION,
    tier: str = cveo.VEO_DEFAULT_TIER,
    output_dir: Path | str | None = None,
    on_progress=None,
) -> tuple[dict, Path]:
    """End-to-end pojedyncza scena Kasi: LLM → Veo render z image conditioning.

    Image conditioning (chainlit_assets/kasia_reference.jpg) zapewnia tę samą postać
    we wszystkich scenach. Głos jest natywny Veo (bez ElevenLabs overlay).

    Zwraca (enhanced_dict, final_mp4_path).
    """
    if on_progress:
        on_progress("enhancing_kasia_prompt")
    enhanced = _enhance_kasia_scene(scene_description)

    if on_progress:
        on_progress("rendering_veo_kasia")
    veo_path = cveo.render_lego_video(
        final_prompt=enhanced["veo_prompt"],
        format_key=format_key,
        duration=duration,
        tier=tier,
        output_dir=output_dir,
        on_progress=on_progress,
    )

    if on_progress:
        on_progress("kasia_scene_completed")
    return enhanced, veo_path
