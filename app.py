"""Actio Marketing — Chainlit panel.

Funkcjonalność:
- Dashboard z 3 wykresami (leady per dzień, Lost IS trend, GSC pozycje)
- Conversational chat z Sonnet 4.6 (tool calling do DB)
- Lista raportów `/md-reports/` + render markdown
- Eksport CSV (z bieżących tabel) i PDF (z raportu)
- Banner aktywnych alertów + feed alertów
- Quick actions: generuj raport / sync / dzisiejsze leady
- Filtr data range (slider 7/14/30/60/90/180/365 + custom)
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
from datetime import datetime, timezone

import chainlit as cl
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import alerts
import analyze  # ładuje env z .mcp.json przy imporcie
import chainlit_audio as caud
import chainlit_eleven_gen as celeven
import chainlit_image_gen as cig
import chainlit_kasia_gen as ckasia
import chainlit_reklama_gen as creklama
import chainlit_veo_gen as cveo
import chainlit_video_gen as cvg
import db
import panel_positive_report as ppr


# ── Konfiguracja ──────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "marketing_data.db")
MD_REPORTS_DIR = os.environ.get("MD_REPORTS_DIR", "./md-reports")
MD_FULL_DIR = os.environ.get("MD_FULL_DIR", "./md-full")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAINLIT_CHAT_MODEL", "anthropic/claude-sonnet-4.6")
CHAINLIT_DB_PATH = os.environ.get(
    "CHAINLIT_DB_PATH",
    str(pathlib.Path(DB_PATH).parent / "chainlit_data.db"),
)

DEFAULT_DAYS = 30
DAYS_OPTIONS = [7, 14, 30, 60, 90, 180, 365]


# ── Chainlit Data Layer (SQLAlchemy + SQLite) ────────────────────────────────
# Self-hosted persistent chat history — pojawia się jako sidebar w UI.

def _init_chainlit_schema() -> None:
    """Tworzy 5 tabel Chainlit w osobnej bazie SQLite (idempotent)."""
    import sqlite3
    schema_path = pathlib.Path(__file__).parent / "chainlit_schema.sql"
    if not schema_path.exists():
        return
    conn = sqlite3.connect(CHAINLIT_DB_PATH)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


_init_chainlit_schema()

try:
    import chainlit.data as cl_data
    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
    cl_data._data_layer = SQLAlchemyDataLayer(
        conninfo=f"sqlite+aiosqlite:///{CHAINLIT_DB_PATH}",
    )
except Exception as _e:
    print(f"Chainlit data layer init failed (continuing without persistence): {_e}")


# ── Helpery sesji ─────────────────────────────────────────────────────────────

def _days() -> int:
    return int(cl.user_session.get("days") or DEFAULT_DAYS)


def _set_mode(mode: str) -> None:
    cl.user_session.set("mode", mode)


def _mode() -> str:
    return cl.user_session.get("mode") or "menu"


# ── Banner alertów ────────────────────────────────────────────────────────────

# Whitelist CEO-style emails (positive view, bez technicznych alertów)
CEO_EMAILS = {"hubert.porebski@actio.pl"}


def _is_ceo_user(user_email: str | None) -> bool:
    if not user_email:
        return False
    return user_email.lower() in {e.lower() for e in CEO_EMAILS}


async def _send_alert_banner() -> None:
    """Wysyła wiadomość z banner-em jeśli są nierozwiązane alerty. CMO only."""
    try:
        df = db.fetch_recent_alerts(DB_PATH, limit=5, only_unresolved=True)
    except Exception:
        return
    if df.empty:
        return
    items = "\n".join(f"- **{r['type']}** · {r['triggered_at']}: {r['message'][:120]}" for _, r in df.iterrows())
    await cl.Message(
        author="🚨 Alerty",
        content=f"### ⚠️ Aktywne alerty ({len(df)})\n\n{items}\n\n_Wybierz **Alerty** w menu żeby zarządzać._",
    ).send()


async def _send_ceo_welcome() -> None:
    """Krótki welcome dla CEO — bez metryk (te są w Raporcie)."""
    await cl.Message(
        author="Actio Marketing",
        content=(
            "### 👋 Cześć, Hubert!\n\n"
            "Z menu poniżej wybierz **📄 Raport** (dzisiejszy raport z maila), "
            "**📊 Dashboard** (wykresy), **📈 Dzisiejsze leady** lub **💬 Chat z asystentem**."
        ),
    ).send()


async def _render_ceo_report() -> None:
    """CEO Raport = treść codziennego maila (panel_positive_report.generate)."""
    try:
        pkg = ppr.generate()  # zwraca {subject, plain, html}
        await cl.Message(
            author="Actio Marketing Report",
            content=pkg["plain"],
        ).send()
    except Exception as e:
        await cl.Message(
            author="Actio Marketing",
            content=f"⚠️ Nie udało się wygenerować raportu: {type(e).__name__}: {e}",
        ).send()


# ── Główne menu ───────────────────────────────────────────────────────────────

MENU_ACTIONS = [
    cl.Action(name="dashboard", value="dashboard", label="📊 Dashboard", payload={}),
    cl.Action(name="chat", value="chat", label="💬 Chat z asystentem", payload={}),
    cl.Action(name="reports", value="reports", label="📄 Raporty", payload={}),
    cl.Action(name="alerts", value="alerts", label="🚨 Alerty", payload={}),
    cl.Action(name="generate_report", value="generate_report", label="🔄 Wygeneruj raport teraz", payload={}),
    cl.Action(name="sync_all", value="sync_all", label="📥 Sync wszystko", payload={}),
    cl.Action(name="today_leads", value="today_leads", label="📈 Dzisiejsze leady", payload={}),
]

# CEO menu — bez tech triggers (Alerty/Generate/Sync to CMO domain)
MENU_ACTIONS_CEO = [
    cl.Action(name="dashboard", value="dashboard", label="📊 Dashboard", payload={}),
    cl.Action(name="chat", value="chat", label="💬 Chat z asystentem", payload={}),
    cl.Action(name="reports", value="reports", label="📄 Raport", payload={}),
    cl.Action(name="today_leads", value="today_leads", label="📈 Dzisiejsze leady", payload={}),
]


def _current_user_is_ceo() -> bool:
    user = cl.user_session.get("user")
    user_email = (user.identifier if user else "anonymous").lower()
    return _is_ceo_user(user_email)


async def _show_menu(intro: str | None = None) -> None:
    _set_mode("menu")
    is_ceo = _current_user_is_ceo()
    if is_ceo:
        text = intro or "### Wybierz"
        await cl.Message(content=text, actions=MENU_ACTIONS_CEO).send()
    else:
        text = intro or "### Wybierz, co chcesz zobaczyć"
        text += f"\n\n_Aktualny zakres dat: **{_days()} dni** (zmień w Settings ⚙️ — ikona koła zębatego)_"
        await cl.Message(content=text, actions=MENU_ACTIONS).send()


# ── Auth (Cloudflare Access header) ──────────────────────────────────────────

@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    """Identyfikuje usera po Cloudflare Access header `Cf-Access-Authenticated-User-Email`.

    Bez header (np. local dev) zwraca generic 'anonymous' user.
    """
    # Headers w Chainlit są dict z lowercase keys
    email = (
        headers.get('cf-access-authenticated-user-email')
        or headers.get('Cf-Access-Authenticated-User-Email')
        or 'anonymous'
    )
    return cl.User(identifier=email, metadata={"email": email})


# ── on_chat_start ─────────────────────────────────────────────────────────────

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("days", DEFAULT_DAYS)
    _set_mode("menu")

    # Settings (slider zakresu dni 1-365)
    settings = await cl.ChatSettings([
        cl.input_widget.Slider(
            id="days_custom",
            label="Zakres dat (dni)",
            initial=DEFAULT_DAYS,
            min=1,
            max=365,
            step=1,
        ),
    ]).send()

    user = cl.user_session.get("user")
    user_email = (user.identifier if user else "anonymous").lower()
    is_ceo = _is_ceo_user(user_email)

    if is_ceo:
        # CEO view (Hubert): positive metrics, brak alertów
        await _send_ceo_welcome()
    else:
        # CMO view (Tom + reszta): full technical view z alertami
        await _send_alert_banner()
        await cl.Message(
            content=(
                "### Panel Actio Marketing\n\n"
                "Witaj. Wybierz tryb z menu poniżej. Wszystko możesz też zapytać po prostu w chacie — "
                "asystent (Sonnet 4.6) ma dostęp do bazy danych i odpowie po polsku."
            ),
        ).send()
    await _show_menu()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    days = int(settings.get("days_custom") or DEFAULT_DAYS)
    days = max(1, min(365, days))
    cl.user_session.set("days", days)
    await cl.Message(content=f"Zakres ustawiony na **{days} dni**.").send()
    if _mode() == "dashboard":
        await _render_dashboard()


# ── Action handlery ───────────────────────────────────────────────────────────

@cl.action_callback("dashboard")
async def act_dashboard(action):
    _set_mode("dashboard")
    await _render_dashboard()


@cl.action_callback("chat")
async def act_chat(action):
    _set_mode("chat")
    cl.user_session.set("chat_history", [])
    await cl.Message(
        content=(
            "### 💬 Chat z asystentem (Sonnet 4.6)\n\n"
            "Pytaj po polsku. Mam dostęp do bazy: GA4, GSC, Google Ads (kampanie / keywordy / search terms / Lost IS), "
            "leady per landing, live state konta.\n\n"
            "**Przykłady:**\n"
            "- ile leadów przyszło wczoraj z paid?\n"
            "- która kampania ma najniższy CPA?\n"
            "- pokaż top 10 search terms ostatnio\n"
            "- jakie GSC frazy są blisko top 10?\n\n"
            "Wpisz `menu` żeby wrócić."
        ),
    ).send()


@cl.action_callback("reports")
async def act_reports(action):
    _set_mode("reports")
    if _current_user_is_ceo():
        # CEO dostaje treść codziennego maila (panel_positive_report)
        await _render_ceo_report()
    else:
        # CMO: lista wszystkich raportów z md-reports
        await _render_reports_list()


@cl.action_callback("alerts")
async def act_alerts(action):
    _set_mode("alerts")
    await _render_alerts_feed()


@cl.action_callback("generate_report")
async def act_generate_report(action):
    msg = await cl.Message(content="🔄 Generuję raport (sync GA4/GSC/Ads + LLM analiza)... ~30-90s").send()
    try:
        result = await cl.make_async(analyze.generate_report)()
        path = result.get("vault_path", "?")
        n_alerts = len(result.get("alerts", []))
        await cl.Message(
            content=(
                f"✅ Raport wygenerowany.\n\n"
                f"- **Plik**: `{path}`\n"
                f"- **Alerty**: {n_alerts}\n"
                f"- **Email**: wysłany do {result.get('email', {}).get('cmo', {}).get('sent_to', [])}"
            ),
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd: `{type(e).__name__}: {e}`").send()
    await _show_menu()


@cl.action_callback("sync_all")
async def act_sync_all(action):
    msg = await cl.Message(content="📥 Sync GA4 / GSC / Google Ads...").send()
    try:
        status = await cl.make_async(analyze.run_all_syncs)()
        lines = "\n".join(f"- **{k}**: {v}" for k, v in status.items())
        await cl.Message(content=f"### Sync zakończony\n\n{lines}").send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd: `{type(e).__name__}: {e}`").send()
    await _show_menu()


@cl.action_callback("today_leads")
async def act_today_leads(action):
    today = datetime.now(timezone.utc).date().isoformat()
    df = db.fetch_landing_conversions(DB_PATH, days=2, top=50)
    df = df[df["leads"] > 0] if not df.empty else df
    if df.empty:
        await cl.Message(content=f"### Leady (ostatnie 2 dni)\n\n_Brak danych — może GA4 jeszcze nie zsyncowany._").send()
    else:
        await cl.Message(content=f"### Leady — ostatnie 2 dni (per landing × source)\n\n{df.to_markdown(index=False)}").send()
    await _show_menu()


@cl.action_callback("resolve_alert")
async def act_resolve_alert(action):
    alert_id = int(action.payload.get("id", 0))
    if alert_id:
        try:
            db.resolve_alert(DB_PATH, alert_id)
            await cl.Message(content=f"✅ Alert #{alert_id} oznaczony jako rozwiązany.").send()
        except Exception as e:
            await cl.Message(content=f"❌ {e}").send()
    await _render_alerts_feed()


@cl.action_callback("view_report")
async def act_view_report(action):
    """Wyświetla raport z MD_REPORTS_DIR (już zapisany jako panel version przez analyze.py)."""
    filename = action.payload.get("file", "")
    path = pathlib.Path(MD_REPORTS_DIR) / filename
    if not path.exists():
        await cl.Message(content=f"❌ Brak pliku `{filename}`").send()
    else:
        await cl.Message(content=path.read_text(encoding="utf-8")).send()
        # Eksport PDF dla tego raportu
        await cl.Message(
            content=f"_Eksport pliku `{filename}`:_",
            actions=[
                cl.Action(name="export_report_pdf", value=filename, label="📄 Pobierz PDF",
                          payload={"file": filename}),
            ],
        ).send()
    await _render_reports_list()


@cl.action_callback("export_report_pdf")
async def act_export_report_pdf(action):
    """PDF eksport używa panel version (md-reports). Pełna wersja jest w mailu."""
    filename = action.payload.get("file", "")
    path = pathlib.Path(MD_REPORTS_DIR) / filename
    if not path.exists():
        await cl.Message(content=f"❌ Brak pliku `{filename}`").send()
        return
    try:
        import markdown as md_lib
        try:
            from weasyprint import HTML
            html = md_lib.markdown(path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
            full = f"<html><head><meta charset='utf-8'><style>body{{font-family:sans-serif;max-width:780px;margin:24px auto;padding:0 16px;}}table{{border-collapse:collapse;}}th,td{{border:1px solid #ddd;padding:4px 8px;}}</style></head><body>{html}</body></html>"
            pdf_bytes = HTML(string=full).write_pdf()
            pdf_name = filename.replace(".md", ".pdf")
            await cl.Message(
                content=f"✅ PDF gotowy: `{pdf_name}`",
                elements=[cl.File(name=pdf_name, content=pdf_bytes, mime="application/pdf")],
            ).send()
        except ImportError:
            await cl.Message(content="❌ WeasyPrint nie zainstalowany. `uv add weasyprint`").send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd: `{type(e).__name__}: {e}`").send()


@cl.action_callback("video_pick_scene_count")
async def act_video_pick_scene_count(action):
    """Krok 1: wybór liczby scen → set state, pytaj o scenę 1 (state machine via on_message)."""
    payload = action.payload or {}
    count = int(payload.get("count") or action.value or 0)
    dialog_mode = bool(payload.get("dialog_mode"))
    if count < 1 or count > 5:
        await cl.Message(content="Niepoprawna liczba scen.").send()
        return
    cl.user_session.set("video_dialog_mode", dialog_mode)
    cl.user_session.set("video_scenes", [])
    cl.user_session.set("awaiting_scenes_for", "dialog" if dialog_mode else "scenariusz")
    cl.user_session.set("awaiting_scene_count", count)
    if dialog_mode:
        prompt = f"**Scena 1/{count}** – wklej dokładny tekst który Kaśka ma wypowiedzieć (max ~250 słów ≈ 90 s):"
    else:
        prompt = f"**Scena 1/{count}** – podaj temat sceny (LLM napisze skrypt ~90 s):"
    await cl.Message(content=prompt).send()


@cl.action_callback("lego_pick_scene_count")
async def act_lego_pick_scene_count(action):
    """Krok 1: wybór liczby scen Lego → set state, pytaj o scenę 1 (state machine via on_message)."""
    payload = action.payload or {}
    count = int(payload.get("count") or action.value or 0)
    if count < 1 or count > 5:
        await cl.Message(content="Niepoprawna liczba scen.").send()
        return
    cl.user_session.set("lego_scenes", [])
    cl.user_session.set("awaiting_scenes_for", "lego")
    cl.user_session.set("awaiting_scene_count", count)
    await cl.Message(
        content=f"**Scena 1/{count}** – opisz scenę (postacie, otoczenie, akcja, dialogi w cudzysłowach):",
    ).send()


@cl.action_callback("lego_pick_tier")
async def act_lego_pick_tier(action):
    """Krok 2: tier wybrany → format pick (filtrowane do obsługiwanych aspect ratios)."""
    payload = action.payload or {}
    tier = payload.get("tier") or action.value
    if tier not in cveo.VEO_TIERS:
        await cl.Message(content="Nieznany tier.").send()
        return
    scenes = cl.user_session.get("lego_scenes") or []
    if not scenes:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/lego`.").send()
        return
    cl.user_session.set("lego_tier", tier)

    formats = cveo.formats_for_tier(tier)
    actions = [
        cl.Action(name="lego_pick_format", value=key, label=f"{f['label']}", payload={"format": key})
        for key, f in formats.items()
    ]
    tier_info = cveo.VEO_TIERS[tier]
    note = " · Bez 1:1 (square niedostępne dla Lite)." if tier == "lite" else ""
    await cl.Message(
        content=(
            f"**Tier**: {tier_info['label']} – {tier_info['description']}{note}\n\n"
            f"**Krok 3** — wybierz format (wspólny dla wszystkich scen):"
        ),
        actions=actions,
    ).send()


@cl.action_callback("eleven_pick_tier")
async def act_eleven_pick_tier(action):
    """Eleven krok 1/4: tier Seedance → aspect ratio."""
    payload = action.payload or {}
    tier = payload.get("tier") or action.value
    if tier not in celeven.SEEDANCE_TIERS:
        await cl.Message(content="Nieznany tier.").send()
        return
    scenes = cl.user_session.get("eleven_scenes") or []
    if not scenes:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/eleven`.").send()
        return
    cl.user_session.set("eleven_tier", tier)
    actions = [
        cl.Action(name="eleven_pick_aspect", value=ar, label=f"{cfg['label']}",
                  payload={"aspect": ar})
        for ar, cfg in celeven.SEEDANCE_ASPECT_RATIOS.items()
    ]
    await cl.Message(
        content=(
            f"**Tier**: {celeven.SEEDANCE_TIERS[tier]['label']}\n\n"
            f"**Krok 2/4** — wybierz aspect ratio:"
        ),
        actions=actions,
    ).send()


@cl.action_callback("eleven_pick_aspect")
async def act_eleven_pick_aspect(action):
    """Eleven krok 2/4: aspect → muzyka."""
    payload = action.payload or {}
    aspect = payload.get("aspect") or action.value
    if aspect not in celeven.SEEDANCE_ASPECT_RATIOS:
        await cl.Message(content="Nieznany aspect ratio.").send()
        return
    scenes = cl.user_session.get("eleven_scenes") or []
    tier = cl.user_session.get("eleven_tier")
    if not scenes or tier not in celeven.SEEDANCE_TIERS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/eleven`.").send()
        return
    cl.user_session.set("eleven_aspect", aspect)
    actions = [
        cl.Action(name="eleven_pick_music", value="yes",
                  label="Tak (+$0,04 Lyria)", payload={"music": "yes"}),
        cl.Action(name="eleven_pick_music", value="no",
                  label="Nie (sam Riley)", payload={"music": "no"}),
    ]
    await cl.Message(
        content=(
            f"**Tier**: {celeven.SEEDANCE_TIERS[tier]['label']} · "
            f"**Aspect**: {celeven.SEEDANCE_ASPECT_RATIOS[aspect]['label']}\n\n"
            f"**Krok 3/4** — dodać tło muzyczne Lyria 3 (+$0,04)?\n\n"
            f"_Voice ElevenLabs Riley domyślny dla `/eleven` (tempo 1.0×)._"
        ),
        actions=actions,
    ).send()


@cl.action_callback("eleven_pick_music")
async def act_eleven_pick_music(action):
    """Eleven krok 3/4: muzyka → render N scen × Seedance + Riley overlay + concat + opc Lyria."""
    import datetime
    import time as _time

    payload = action.payload or {}
    music_choice = payload.get("music") or action.value
    scenes = cl.user_session.get("eleven_scenes") or []
    tier = cl.user_session.get("eleven_tier")
    aspect = cl.user_session.get("eleven_aspect")
    if not scenes or tier not in celeven.SEEDANCE_TIERS or aspect not in celeven.SEEDANCE_ASPECT_RATIOS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/eleven`.").send()
        return
    with_music = (music_choice == "yes")

    # Clamp durations do range Seedance 4-15s
    clamped_durations = [
        max(celeven.SEEDANCE_MIN_DURATION, min(celeven.SEEDANCE_MAX_DURATION, int(s["duration_s"])))
        for s in scenes
    ]
    total_s = sum(clamped_durations)
    chars_total = sum(len(s["voiceover"]) for s in scenes)
    veo_cost = total_s * celeven.SEEDANCE_TIERS[tier]["price_per_sec"]
    tts_cost = chars_total * 0.0001
    total_cost = veo_cost + tts_cost + (0.04 if with_music else 0.0)

    intro = (
        f"🎥 **Render Seedance 2.0 startuje** ({len(scenes)} scen, {total_s}s total)\n\n"
        f"- Tier: {celeven.SEEDANCE_TIERS[tier]['label']}\n"
        f"- Aspect: {celeven.SEEDANCE_ASPECT_RATIOS[aspect]['label']}\n"
        f"- Voice: ElevenLabs Riley · Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
        f"- **Łączny koszt**: ${total_cost:.2f}"
    )
    await cl.Message(content=intro).send()
    progress_msg = cl.Message(content="🚀 Inicjalizuję…")
    await progress_msg.send()

    start_ts = _time.time()
    scene_paths: list = []
    ts_global = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    total_scenes = len(scenes)

    try:
        for scene_i, scene in enumerate(scenes, 1):
            duration = clamped_durations[scene_i - 1]
            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(scene_i - 1, total_scenes)}\n\n"
                f"🎬 **Scena {scene_i}/{total_scenes}** ({duration}s, Seedance {tier})\n"
                f"📝 Piszę cinematic prompt (Sonnet 4.6)…\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            seed_prompt = await cl.make_async(celeven._enhance_seedance_prompt)(scene["image"])

            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(scene_i - 1, total_scenes)}\n\n"
                f"🎬 **Scena {scene_i}/{total_scenes}** ({duration}s)\n"
                f"⏳ Seedance 2.0 render ({tier}, {aspect}) – queue + generation (typowo 1-3 min)…\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            clip_path = await cl.make_async(celeven.render_seedance_clip)(
                prompt=seed_prompt,
                aspect_ratio=aspect,
                duration=duration,
                tier=tier,
            )

            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(scene_i - 1, total_scenes)}\n\n"
                f"🎙 **Scena {scene_i}/{total_scenes}** – ElevenLabs Riley TTS ({len(scene['voiceover'])} znaków)…\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            voiced_scene = await cl.make_async(celeven.replace_audio_with_riley)(
                video_path=clip_path,
                voiceover_text=scene["voiceover"],
            )
            scene_paths.append(voiced_scene)

        # Concat scen
        elapsed = int(_time.time() - start_ts)
        progress_msg.content = (
            f"{_progress_bar(total_scenes, total_scenes)}\n\n"
            f"🪢 **Łączę {len(scene_paths)} scen…**\n\n"
            f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
        )
        await progress_msg.update()
        if len(scene_paths) > 1:
            ar_safe = aspect.replace(":", "x")
            final_path = scene_paths[0].parent / f"eleven_{tier}_{ar_safe}_{ts_global}.mp4"
            final_path = await cl.make_async(cveo.concat_videos)(scene_paths, final_path)
        else:
            final_path = scene_paths[0]

        if with_music:
            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(total_scenes, total_scenes)}\n\n"
                f"🎹 **Generuję tło muzyczne (Lyria 3, $0,04)…**\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            try:
                full_voiceover = " ".join(s["voiceover"] for s in scenes)
                final_path, _info = await cl.make_async(caud.add_music_to_video)(
                    video_path=final_path, scene_or_script=full_voiceover,
                )
            except Exception as e:
                await cl.Message(content=f"⚠️ Tło nie udało się ({type(e).__name__}: {e}).").send()

    except Exception as e:
        elapsed = int(_time.time() - start_ts)
        progress_msg.content = f"❌ **Błąd renderu po {elapsed//60}m {elapsed%60}s**: `{type(e).__name__}: {e}`"
        await progress_msg.update()
        return

    total_elapsed = int(_time.time() - start_ts)
    progress_msg.content = (
        f"{_progress_bar(total_scenes, total_scenes)}\n\n"
        f"✅ **Render zakończony w {total_elapsed//60}m {total_elapsed%60}s**"
    )
    await progress_msg.update()

    cl.user_session.set("last_video_path", str(final_path))
    await cl.Message(
        content=(
            f"✅ **Eleven (Seedance 2.0) gotowe.**\n\n"
            f"- Scen: {len(scenes)} · Łączny czas: **{total_s}s**\n"
            f"- Tier: {celeven.SEEDANCE_TIERS[tier]['label']}\n"
            f"- Aspect: {celeven.SEEDANCE_ASPECT_RATIOS[aspect]['label']}\n"
            f"- Voice: ElevenLabs Riley · Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- Łączny koszt: ${total_cost:.2f}\n"
            f"- Plik: `{final_path.name}`"
        ),
        elements=[cl.Video(path=str(final_path), name=final_path.name, display="inline")],
    ).send()
    cl.user_session.set("eleven_scenes", None)
    cl.user_session.set("eleven_tier", None)
    cl.user_session.set("eleven_aspect", None)


@cl.action_callback("reklama_pick_speed")
async def act_reklama_pick_speed(action):
    """Reklama krok 1: tempo lektora → format."""
    payload = action.payload or {}
    speed = float(payload.get("speed") or action.value or 1.0)
    scenes = cl.user_session.get("reklama_scenes") or []
    if not scenes:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/reklama`.").send()
        return
    cl.user_session.set("reklama_speed", speed)
    # Lite tier nie wspiera 1:1 – tylko 9:16 i 16:9
    formats = cveo.formats_for_tier("lite")
    actions = [
        cl.Action(name="reklama_pick_format", value=key, label=f"{f['label']}",
                  payload={"format": key})
        for key, f in formats.items()
    ]
    await cl.Message(
        content=(
            f"**Tempo lektora**: {speed}× · **Tier**: Veo Lite (hardcoded)\n\n"
            f"**Krok 2/3** — wybierz format:"
        ),
        actions=actions,
    ).send()


@cl.action_callback("reklama_pick_format")
async def act_reklama_pick_format(action):
    """Reklama krok 2: format → muzyka."""
    payload = action.payload or {}
    format_key = payload.get("format") or action.value
    scenes = cl.user_session.get("reklama_scenes") or []
    speed = float(cl.user_session.get("reklama_speed") or 1.0)
    if not scenes or format_key not in cveo.VEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/reklama`.").send()
        return
    cl.user_session.set("reklama_format", format_key)
    fmt = cveo.VEO_FORMATS[format_key]
    actions = [
        cl.Action(name="reklama_pick_music", value="yes",
                  label="Tak (+$0,04 Lyria)", payload={"music": "yes"}),
        cl.Action(name="reklama_pick_music", value="no",
                  label="Nie (sam voice-over)", payload={"music": "no"}),
    ]
    await cl.Message(
        content=(
            f"**Tempo**: {speed}× · **Format**: {fmt['label']} · **Tier**: Veo Lite\n\n"
            f"**Krok 3/3** — dodać tło muzyczne (Lyria 3, +$0,04 pod całość)?"
        ),
        actions=actions,
    ).send()


def _progress_bar(done: int, total: int, width: int = 20) -> str:
    """Renderuje pasek typu `[████████░░░░░░░░░░░░] 8/20`."""
    if total <= 0:
        return ""
    filled = int(done * width / total)
    return f"`[{'█' * filled}{'░' * (width - filled)}] {done}/{total}`"


@cl.action_callback("reklama_pick_music")
async def act_reklama_pick_music(action):
    """Reklama krok 3: muzyka → orchestracja chunk-by-chunk z progress bar updateowany w realtime."""
    import datetime
    import time as _time

    payload = action.payload or {}
    music_choice = payload.get("music") or action.value
    scenes = cl.user_session.get("reklama_scenes") or []
    speed = float(cl.user_session.get("reklama_speed") or 1.0)
    format_key = cl.user_session.get("reklama_format")
    if not scenes or format_key not in cveo.VEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/reklama`.").send()
        return
    with_music = (music_choice == "yes")
    fmt = cveo.VEO_FORMATS[format_key]
    tier = "lite"

    # Plan chunks dla progress bar
    scene_chunk_plan = [creklama.split_to_veo_chunks(s["duration_s"]) for s in scenes]
    total_chunks = sum(len(c) for c in scene_chunk_plan)
    chunk_seconds_total = sum(sum(c) for c in scene_chunk_plan)
    chars_total = sum(len(s["voiceover"]) for s in scenes)
    veo_cost = chunk_seconds_total * cveo.VEO_TIERS[tier]["price_per_sec"]
    tts_cost = chars_total * 0.0001
    total_cost = veo_cost + tts_cost + (0.04 if with_music else 0.0)

    intro = (
        f"📺 **Render reklamy startuje** ({len(scenes)} scen, "
        f"{sum(s['duration_s'] for s in scenes)}s total, {total_chunks} chunków Veo)\n\n"
        f"- Tier: Veo Lite · Format: {fmt['label']}\n"
        f"- Tempo: {speed}× · Voice: ElevenLabs Maria · Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
        f"- **Łączny koszt**: ${total_cost:.2f}\n"
    )
    await cl.Message(content=intro).send()

    # Live progress message (updateowana w trakcie)
    progress_msg = cl.Message(content="🚀 Inicjalizuję…")
    await progress_msg.send()

    start_ts = _time.time()
    chunks_done = 0
    scene_paths: list = []
    ts_global = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        for scene_i, scene in enumerate(scenes, 1):
            chunks = scene_chunk_plan[scene_i - 1]

            # Krok 1: enhance prompt LLM
            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(chunks_done, total_chunks)}\n\n"
                f"🎬 **Scena {scene_i}/{len(scenes)}** ({scene['duration_s']}s)\n"
                f"📝 Piszę cinematic prompt Veo (Sonnet 4.6)…\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            veo_prompt = await cl.make_async(creklama.enhance_broll_prompt)(scene["image"])

            # Krok 2: render N chunków Veo
            chunk_paths: list = []
            for chunk_i, chunk_dur in enumerate(chunks, 1):
                elapsed = int(_time.time() - start_ts)
                progress_msg.content = (
                    f"{_progress_bar(chunks_done, total_chunks)}\n\n"
                    f"🎬 **Scena {scene_i}/{len(scenes)}** ({scene['duration_s']}s)\n"
                    f"⏳ Veo chunk {chunk_i}/{len(chunks)} ({chunk_dur}s) – render (typowo 2-3 min, max 30 min timeout)…\n\n"
                    f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
                )
                await progress_msg.update()
                p = await cl.make_async(cveo.render_lego_video)(
                    final_prompt=veo_prompt,
                    format_key=format_key,
                    duration=chunk_dur,
                    tier=tier,
                )
                chunk_paths.append(p)
                chunks_done += 1

            # Krok 3: concat chunków per scena
            if len(chunk_paths) > 1:
                elapsed = int(_time.time() - start_ts)
                progress_msg.content = (
                    f"{_progress_bar(chunks_done, total_chunks)}\n\n"
                    f"🎬 **Scena {scene_i}/{len(scenes)}** – łączę {len(chunk_paths)} chunków…\n\n"
                    f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
                )
                await progress_msg.update()
                scene_video = chunk_paths[0].parent / f"reklama_chunks_s{scene_i}_{ts_global}.mp4"
                scene_video = await cl.make_async(cveo.concat_videos)(chunk_paths, scene_video)
            else:
                scene_video = chunk_paths[0]

            # Krok 4: voice-over ElevenLabs
            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(chunks_done, total_chunks)}\n\n"
                f"🎙 **Scena {scene_i}/{len(scenes)}** – ElevenLabs Maria TTS ({len(scene['voiceover'])} znaków, tempo {speed}×)…\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            voiced_scene = await cl.make_async(creklama.replace_audio_with_voiceover)(
                video_path=scene_video,
                voiceover_text=scene["voiceover"],
                speed=speed,
            )
            scene_paths.append(voiced_scene)

        # Krok 5: concat wszystkich scen
        elapsed = int(_time.time() - start_ts)
        progress_msg.content = (
            f"{_progress_bar(chunks_done, total_chunks)}\n\n"
            f"🪢 **Łączę {len(scene_paths)} scen w finalne wideo…**\n\n"
            f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
        )
        await progress_msg.update()
        if len(scene_paths) > 1:
            final_path = scene_paths[0].parent / f"reklama_{tier}_{format_key}_{ts_global}.mp4"
            final_path = await cl.make_async(cveo.concat_videos)(scene_paths, final_path)
        else:
            final_path = scene_paths[0]

        # Krok 6: optional Lyria music
        if with_music:
            elapsed = int(_time.time() - start_ts)
            progress_msg.content = (
                f"{_progress_bar(chunks_done, total_chunks)}\n\n"
                f"🎹 **Generuję tło muzyczne (Lyria 3, $0,04)…**\n\n"
                f"_⏱ {elapsed//60}m {elapsed%60}s od startu_"
            )
            await progress_msg.update()
            try:
                full_voiceover = " ".join(s["voiceover"] for s in scenes)
                final_path, _info = await cl.make_async(caud.add_music_to_video)(
                    video_path=final_path, scene_or_script=full_voiceover,
                )
            except Exception as e:
                await cl.Message(content=f"⚠️ Tło muzyczne nie udało się ({type(e).__name__}: {e}). Wysyłam bez muzyki.").send()

    except Exception as e:
        elapsed = int(_time.time() - start_ts)
        progress_msg.content = f"❌ **Błąd renderu po {elapsed//60}m {elapsed%60}s**: `{type(e).__name__}: {e}`"
        await progress_msg.update()
        return

    total_elapsed = int(_time.time() - start_ts)
    progress_msg.content = (
        f"{_progress_bar(chunks_done, total_chunks)}\n\n"
        f"✅ **Render zakończony w {total_elapsed//60}m {total_elapsed%60}s**"
    )
    await progress_msg.update()

    cl.user_session.set("last_video_path", str(final_path))
    await cl.Message(
        content=(
            f"✅ **Reklama gotowa.**\n\n"
            f"- Scen: {len(scenes)} · Łączny czas: **{sum(s['duration_s'] for s in scenes)}s**\n"
            f"- Chunków Veo: {total_chunks} · Tempo lektora: {speed}×\n"
            f"- Tier: Veo Lite · Format: {fmt['label']}\n"
            f"- Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- Łączny koszt: ${total_cost:.2f}\n"
            f"- Plik: `{final_path.name}`"
        ),
        elements=[cl.Video(path=str(final_path), name=final_path.name, display="inline")],
    ).send()
    cl.user_session.set("reklama_scenes", None)
    cl.user_session.set("reklama_speed", None)
    cl.user_session.set("reklama_format", None)


@cl.action_callback("kasia_pick_scene_count")
async def act_kasia_pick_scene_count(action):
    """Kasia krok 1: liczba scen → state machine via on_message."""
    payload = action.payload or {}
    count = int(payload.get("count") or action.value or 0)
    if count < 1 or count > 5:
        await cl.Message(content="Niepoprawna liczba scen.").send()
        return
    cl.user_session.set("kasia_scenes", [])
    cl.user_session.set("awaiting_scenes_for", "kasia")
    cl.user_session.set("awaiting_scene_count", count)
    await cl.Message(
        content=f"**Scena 1/{count}** – opisz co Kasia robi/o czym mówi (np. 'Tłumaczy korzyści VoIP dla MŚP'):",
    ).send()


@cl.action_callback("kasia_pick_tier")
async def act_kasia_pick_tier(action):
    """Kasia krok 2: tier → format."""
    payload = action.payload or {}
    tier = payload.get("tier") or action.value
    if tier not in cveo.VEO_TIERS:
        await cl.Message(content="Nieznany tier.").send()
        return
    scenes = cl.user_session.get("kasia_scenes") or []
    if not scenes:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/kasia`.").send()
        return
    cl.user_session.set("kasia_tier", tier)
    formats = cveo.formats_for_tier(tier)
    actions = [
        cl.Action(name="kasia_pick_format", value=key, label=f"{f['label']}", payload={"format": key})
        for key, f in formats.items()
    ]
    tier_info = cveo.VEO_TIERS[tier]
    note = " · Bez 1:1 (Lite nie wspiera square)." if tier == "lite" else ""
    await cl.Message(
        content=(
            f"**Tier**: {tier_info['label']} – {tier_info['description']}{note}\n\n"
            f"**Krok 3** — format (wspólny dla wszystkich scen):"
        ),
        actions=actions,
    ).send()


@cl.action_callback("kasia_pick_format")
async def act_kasia_pick_format(action):
    """Kasia krok 3: format → długość."""
    payload = action.payload or {}
    format_key = payload.get("format") or action.value
    scenes = cl.user_session.get("kasia_scenes") or []
    tier = cl.user_session.get("kasia_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/kasia`.").send()
        return
    cl.user_session.set("kasia_format", format_key)
    fmt = cveo.VEO_FORMATS[format_key]
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    actions = [
        cl.Action(name="kasia_pick_duration", value=str(d),
                  label=f"{d}s (${d * price_per_sec * len(scenes):.2f} Veo total)",
                  payload={"duration": d})
        for d in cveo.VEO_DURATIONS
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} · **Tier**: {cveo.VEO_TIERS[tier]['label']} · "
            f"**Format**: {fmt['label']}\n\n"
            f"**Krok 4** — długość per scena:"
        ),
        actions=actions,
    ).send()


@cl.action_callback("kasia_pick_duration")
async def act_kasia_pick_duration(action):
    """Kasia krok 4: długość → muzyka."""
    payload = action.payload or {}
    duration = int(payload.get("duration") or action.value or 0)
    scenes = cl.user_session.get("kasia_scenes") or []
    format_key = cl.user_session.get("kasia_format")
    tier = cl.user_session.get("kasia_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS or duration not in cveo.VEO_DURATIONS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/kasia`.").send()
        return
    cl.user_session.set("kasia_duration", duration)
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    veo_cost = duration * price_per_sec * len(scenes)

    actions = [
        cl.Action(name="kasia_pick_music", value="yes",
                  label="Tak (+$0,04 Lyria)", payload={"music": "yes"}),
        cl.Action(name="kasia_pick_music", value="no",
                  label="Nie (natywny Veo audio)", payload={"music": "no"}),
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} × {duration}s · **Tier**: {cveo.VEO_TIERS[tier]['label']} · "
            f"**Format**: {cveo.VEO_FORMATS[format_key]['label']}\n"
            f"**Łączny czas**: {len(scenes) * duration}s · **Veo total**: ${veo_cost:.2f}\n\n"
            f"**Krok 5** — dodać tło muzyczne (Lyria 3 +$0,04 pod całość)?"
        ),
        actions=actions,
    ).send()


@cl.action_callback("kasia_pick_music")
async def act_kasia_pick_music(action):
    """Kasia krok 5: muzyka → render N scen (Veo + ElevenLabs voice overlay per scena) + concat + opc Lyria."""
    payload = action.payload or {}
    music_choice = payload.get("music") or action.value
    scenes = cl.user_session.get("kasia_scenes") or []
    duration = int(cl.user_session.get("kasia_duration") or 0)
    format_key = cl.user_session.get("kasia_format")
    tier = cl.user_session.get("kasia_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS or duration not in cveo.VEO_DURATIONS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/kasia`.").send()
        return
    with_music = (music_choice == "yes")

    fmt = cveo.VEO_FORMATS[format_key]
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    veo_cost = duration * price_per_sec * len(scenes)
    total_cost = veo_cost + (0.04 if with_music else 0.0)

    ref_status = "✓ image conditioning" if ckasia.KASIA_REFERENCE_IMAGE.exists() else "⚠️ brak ref image"
    await cl.Message(
        content=(
            f"👩‍💼 **Generuję {len(scenes)} {'scenę' if len(scenes)==1 else 'scen'} z Kasią "
            f"({cveo.VEO_TIERS[tier]['label']})…**\n\n"
            f"- Format: {fmt['label']} · Długość/scena: {duration}s · {ref_status}\n"
            f"- Audio: natywny Veo · Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- **Łączny koszt**: ${total_cost:.2f}"
        ),
    ).send()

    paths: list = []
    all_dialogs: list[str] = []
    try:
        for i, scene in enumerate(scenes, 1):
            await cl.Message(content=f"🎬 **Scena {i}/{len(scenes)}** – LLM prompt + Veo render (image-conditioned)…").send()
            enhanced, p = await cl.make_async(ckasia.render_kasia_scene)(
                scene_description=scene,
                format_key=format_key,
                duration=duration,
                tier=tier,
            )
            paths.append(p)
            all_dialogs.append(enhanced["tts_text"])
            await cl.Message(
                content=(
                    f"  ✓ Scena {i}/{len(scenes)}: `{p.name}`\n"
                    f"  📜 Planowany dialog: {enhanced['tts_text'][:200]}"
                ),
            ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd renderu Kasi: `{type(e).__name__}: {e}`").send()
        return

    if len(paths) > 1:
        await cl.Message(content=f"🪢 **Łączę {len(paths)} klipów…**").send()
        try:
            import datetime as _dt
            concat_out = paths[0].parent / f"kasia_{tier}_{format_key}_concat_{_dt.datetime.now():%Y%m%d_%H%M%S}.mp4"
            final_path = await cl.make_async(cveo.concat_videos)(paths, concat_out)
        except Exception as e:
            await cl.Message(content=f"❌ Concat: `{type(e).__name__}: {e}`. Wysyłam scenę 1.").send()
            final_path = paths[0]
    else:
        final_path = paths[0]

    if with_music:
        await cl.Message(content=f"🎹 **Generuję tło muzyczne (Lyria 3, $0,04)…**").send()
        try:
            combined = " | ".join(all_dialogs)
            mixed_path, music_info = await cl.make_async(caud.add_music_to_video)(
                video_path=final_path, scene_or_script=combined,
            )
            final_path = mixed_path
            await cl.Message(
                content=f"🎶 **Tło dodane.**\n\n> {music_info['music_prompt'][:300]}",
            ).send()
        except Exception as e:
            await cl.Message(content=f"⚠️ Tło nie udało się ({type(e).__name__}: {e}).").send()

    cl.user_session.set("last_video_path", str(final_path))
    await cl.Message(
        content=(
            f"✅ **Kasia wideo gotowe.**\n\n"
            f"- Scen: {len(scenes)} × {duration}s = **{len(scenes) * duration}s** total\n"
            f"- Tier: {cveo.VEO_TIERS[tier]['label']} · Format: {fmt['label']}\n"
            f"- Audio: natywny Veo · Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- Łączny koszt: ${total_cost:.2f}\n"
            f"- Plik: `{final_path.name}`\n\n"
            f"_Jeśli głos Veo niesatysfakcjonujący: `/tekst <olka|kaska|marta> <nowy tekst>` podmieni audio._"
        ),
        elements=[cl.Video(path=str(final_path), name=final_path.name, display="inline")],
    ).send()
    cl.user_session.set("kasia_scenes", None)
    cl.user_session.set("kasia_format", None)
    cl.user_session.set("kasia_duration", None)
    cl.user_session.set("kasia_tier", None)


@cl.action_callback("video_pick_avatar")
async def act_video_pick_avatar(action):
    """Krok 2: awatar wybrany → pytaj o głos."""
    payload = action.payload or {}
    avatar_key = payload.get("avatar") or action.value
    scenes = cl.user_session.get("video_scenes") or []
    if not scenes or avatar_key not in cvg.AVATARS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/scenariusz` lub `/dialog`.").send()
        return
    cl.user_session.set("video_avatar", avatar_key)
    actions = [
        cl.Action(name="video_pick_voice", value=key, label=f"{v['label']}",
                  payload={"voice": key})
        for key, v in cvg.VOICES.items()
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} · **Awatar**: {cvg.AVATARS[avatar_key]['label']}\n\n"
            f"**Krok 3** — wybierz głos:"
        ),
        actions=actions,
    ).send()


@cl.action_callback("video_pick_voice")
async def act_video_pick_voice(action):
    """Krok 3: głos wybrany → pytaj o format."""
    payload = action.payload or {}
    voice_key = payload.get("voice") or action.value
    scenes = cl.user_session.get("video_scenes") or []
    avatar_key = cl.user_session.get("video_avatar")
    if not scenes or voice_key not in cvg.VOICES or avatar_key not in cvg.AVATARS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/scenariusz` lub `/dialog`.").send()
        return
    cl.user_session.set("video_voice", voice_key)
    actions = [
        cl.Action(name="video_pick_format", value=key,
                  label=f"{f['label']} ({f['width']}×{f['height']})",
                  payload={"format": key})
        for key, f in cvg.VIDEO_FORMATS.items()
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} · **Awatar**: {cvg.AVATARS[avatar_key]['label']} · "
            f"**Głos**: {cvg.VOICES[voice_key]['label']}\n\n"
            f"**Krok 4** — wybierz format (wspólny dla wszystkich scen):"
        ),
        actions=actions,
    ).send()


@cl.action_callback("video_pick_format")
async def act_video_pick_format(action):
    """Krok 4: format wybrany → pytaj o muzykę."""
    payload = action.payload or {}
    format_key = payload.get("format") or action.value
    scenes = cl.user_session.get("video_scenes") or []
    voice_key = cl.user_session.get("video_voice")
    avatar_key = cl.user_session.get("video_avatar")
    if not scenes or avatar_key not in cvg.AVATARS or voice_key not in cvg.VOICES or format_key not in cvg.VIDEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/scenariusz` lub `/dialog`.").send()
        return
    cl.user_session.set("video_format", format_key)
    dialog_mode = cl.user_session.get("video_dialog_mode") or False

    fmt = cvg.VIDEO_FORMATS[format_key]
    actions = [
        cl.Action(name="video_pick_music", value="yes",
                  label="Tak (+$0,04 Lyria)", payload={"music": "yes"}),
        cl.Action(name="video_pick_music", value="no",
                  label="Nie (sam głos)", payload={"music": "no"}),
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} ({'Dialog 1:1' if dialog_mode else 'Scenariusz LLM'}) · "
            f"**Awatar**: {cvg.AVATARS[avatar_key]['label']} · "
            f"**Głos**: {cvg.VOICES[voice_key]['label']} · "
            f"**Format**: {fmt['label']}\n\n"
            f"**Krok 5** — dodać tło muzyczne (Lyria 3, +$0,04 pod całość)?"
        ),
        actions=actions,
    ).send()


@cl.action_callback("video_pick_music")
async def act_video_pick_music(action):
    """Krok 5: muzyka wybrana → render N scen HeyGen + concat + opcjonalnie Lyria mix."""
    payload = action.payload or {}
    music_choice = payload.get("music") or action.value
    scenes = cl.user_session.get("video_scenes") or []
    format_key = cl.user_session.get("video_format")
    voice_key = cl.user_session.get("video_voice")
    avatar_key = cl.user_session.get("video_avatar")
    if not scenes or avatar_key not in cvg.AVATARS or voice_key not in cvg.VOICES or format_key not in cvg.VIDEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/scenariusz` lub `/dialog`.").send()
        return

    with_music = (music_choice == "yes")
    dialog_mode = cl.user_session.get("video_dialog_mode") or False
    avatar = cvg.AVATARS[avatar_key]
    voice = cvg.VOICES[voice_key]
    fmt = cvg.VIDEO_FORMATS[format_key]
    speed = voice.get("default_speed", 1.0)

    mode_label = "Dialog (1:1)" if dialog_mode else "Scenariusz (LLM)"
    await cl.Message(
        content=(
            f"🎬 **Generuję {len(scenes)} {'scenę' if len(scenes)==1 else 'scen'} ({mode_label})…**\n\n"
            f"- **Awatar**: {avatar['label']} · **Głos**: {voice['label']} (tempo {speed}×)\n"
            f"- **Format**: {fmt['label']} ({fmt['width']}×{fmt['height']})\n"
            f"- **Tło**: {'Lyria 3 ✓ (+$0,04)' if with_music else 'brak'}\n\n"
            f"Krok 1/3: przygotowuję skrypty…"
        ),
    ).send()

    # Build scripts per scene (LLM dla scenariusz, raw dla dialog)
    scripts: list[str] = []
    try:
        for i, scene_input in enumerate(scenes, 1):
            if dialog_mode:
                scripts.append(scene_input)
            else:
                s = await cl.make_async(cvg.generate_script)(scene_input, duration_sec=cvg.DEFAULT_DURATION_SEC)
                scripts.append(s)
                await cl.Message(
                    content=(
                        f"📝 **Scena {i}/{len(scenes)}** ({len(s.split())} słów, ~{len(s.split())*60//145}s):\n\n"
                        f"> {s[:400]}{'...' if len(s) > 400 else ''}"
                    ),
                ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd generowania skryptu: `{type(e).__name__}: {e}`").send()
        return

    # Render każdej sceny przez HeyGen sekwencyjnie
    await cl.Message(
        content=f"🎥 **Krok 2/3: render {len(scenes)} klipów HeyGen** (~3-5 min/klip)…",
    ).send()
    paths: list = []
    try:
        for i, script in enumerate(scripts, 1):
            await cl.Message(content=f"  ↻ Scena {i}/{len(scenes)}…").send()
            p = await cl.make_async(cvg.render_video)(
                script=script, avatar_key=avatar_key, voice_key=voice_key, format_key=format_key,
            )
            paths.append(p)
            await cl.Message(content=f"  ✓ Scena {i}/{len(scenes)}: `{p.name}`").send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd renderu HeyGen: `{type(e).__name__}: {e}`").send()
        return

    # Concat
    if len(paths) > 1:
        await cl.Message(content=f"🪢 **Krok 3/3: łączę {len(paths)} klipów…**").send()
        try:
            import datetime as _dt
            concat_out = paths[0].parent / f"video_{avatar_key}_{voice_key}_{format_key}_concat_{_dt.datetime.now():%Y%m%d_%H%M%S}.mp4"
            final_path = await cl.make_async(cveo.concat_videos)(paths, concat_out)
        except Exception as e:
            await cl.Message(content=f"❌ Błąd concat: `{type(e).__name__}: {e}`. Wysyłam scenę 1.").send()
            final_path = paths[0]
    else:
        final_path = paths[0]

    # Opcjonalna muzyka pod całość
    if with_music:
        await cl.Message(content=f"🎹 **Generuję tło muzyczne (Lyria 3 Clip, $0,04)…**").send()
        try:
            combined_text = " | ".join(scripts)
            mixed_path, music_info = await cl.make_async(caud.add_music_to_video)(
                video_path=final_path, scene_or_script=combined_text,
            )
            final_path = mixed_path
            await cl.Message(
                content=(
                    f"🎶 **Tło dodane.**\n\n"
                    f"> {music_info['music_prompt'][:300]}{'...' if len(music_info['music_prompt']) > 300 else ''}"
                ),
            ).send()
        except Exception as e:
            await cl.Message(
                content=f"⚠️ Tło muzyczne nie udało się ({type(e).__name__}: {e}). Wysyłam bez muzyki.",
            ).send()

    cl.user_session.set("last_video_path", str(final_path))
    await cl.Message(
        content=(
            f"✅ **Film gotowy.**\n\n"
            f"- Scen: {len(scenes)} · Tryb: {mode_label}\n"
            f"- Awatar: {avatar['label']} · Głos: {voice['label']} · Format: {fmt['label']}\n"
            f"- Tło: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- Plik: `{final_path.name}`\n\n"
            f"_`/tekst <olka|kaska|marta> <nowy tekst>` żeby podmienić ścieżkę audio._"
        ),
        elements=[cl.Video(path=str(final_path), name=final_path.name, display="inline")],
    ).send()
    cl.user_session.set("video_scenes", None)
    cl.user_session.set("video_avatar", None)
    cl.user_session.set("video_voice", None)
    cl.user_session.set("video_format", None)
    cl.user_session.set("video_dialog_mode", None)


@cl.action_callback("film_menu_scenariusz")
async def act_film_menu_scenariusz(action):
    await cl.Message(
        content=(
            "Wpisz teraz: `/scenariusz <temat>`\n\n"
            "Przykład: `/scenariusz Wirtualny numer w 24h - korzyści dla firm B2B`"
        ),
    ).send()


@cl.action_callback("film_menu_dialog")
async def act_film_menu_dialog(action):
    await cl.Message(
        content=(
            "Wpisz teraz: `/dialog <gotowy tekst>`\n\n"
            "Przykład: `/dialog Cześć! Tu Kaśka z Actio. Pokażę Ci, jak w 24 h uruchomić wirtualny numer firmowy bez sprzętu.`"
        ),
    ).send()


@cl.action_callback("film_menu_lego")
async def act_film_menu_lego(action):
    await cl.Message(
        content=(
            "Wpisz teraz: `/lego`\n\n"
            "Zostaniesz zapytany o liczbę scen (1–5), potem opisz każdą po kolei. "
            "Przykład opisu sceny: `Dwie postaci w biurze – jedna pyta o Actio, druga z entuzjazmem opowiada o VoIP.`"
        ),
    ).send()


@cl.action_callback("film_menu_reklama")
async def act_film_menu_reklama(action):
    await cl.Message(
        content=(
            "Wpisz teraz: `/reklama`\n\n"
            "Zostaniesz poproszony o wklejenie pełnego scenariusza – timeline + opisy scen + tekst lektora. "
            "LLM sparsuje, potem wybierzesz tempo lektora, format, i muzykę."
        ),
    ).send()


@cl.action_callback("film_menu_kasia")
async def act_film_menu_kasia(action):
    await cl.Message(
        content=(
            "Wpisz teraz: `/kasia`\n\n"
            "Kasia to pracowniczka biura Actio (doradca biznesowy B2B). Veo 3.1 renderuje wideo, "
            "ElevenLabs Maria nakłada spójny głos PL.\n\n"
            "Przykład opisu sceny: `Tłumaczy korzyści wirtualnego numeru dla małych firm.`"
        ),
    ).send()


@cl.action_callback("lego_pick_format")
async def act_lego_pick_format(action):
    """Krok 3: format wybrany → wybór długości (per scena, wspólny)."""
    payload = action.payload or {}
    format_key = payload.get("format") or action.value
    scenes = cl.user_session.get("lego_scenes") or []
    tier = cl.user_session.get("lego_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/lego`.").send()
        return
    cl.user_session.set("lego_format", format_key)
    fmt = cveo.VEO_FORMATS[format_key]
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    actions = [
        cl.Action(
            name="lego_pick_duration",
            value=str(d),
            label=f"{d}s (${d * price_per_sec * len(scenes):.2f} total)",
            payload={"duration": d},
        )
        for d in cveo.VEO_DURATIONS
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} · **Tier**: {cveo.VEO_TIERS[tier]['label']} · "
            f"**Format**: {fmt['label']}\n\n"
            f"**Krok 4** — długość per scena (suma kosztu × {len(scenes)} scen):"
        ),
        actions=actions,
    ).send()


@cl.action_callback("lego_pick_duration")
async def act_lego_pick_duration(action):
    """Krok 4: długość per scena → pytaj o tło muzyczne."""
    payload = action.payload or {}
    duration = int(payload.get("duration") or action.value or 0)
    scenes = cl.user_session.get("lego_scenes") or []
    format_key = cl.user_session.get("lego_format")
    tier = cl.user_session.get("lego_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS or duration not in cveo.VEO_DURATIONS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/lego`.").send()
        return
    cl.user_session.set("lego_duration", duration)
    fmt = cveo.VEO_FORMATS[format_key]
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    veo_cost_total = duration * price_per_sec * len(scenes)

    actions = [
        cl.Action(name="lego_pick_music", value="yes",
                  label="Tak (+$0,04 Lyria)",
                  payload={"music": "yes"}),
        cl.Action(name="lego_pick_music", value="no",
                  label="Nie (tylko Veo audio)",
                  payload={"music": "no"}),
    ]
    await cl.Message(
        content=(
            f"**Scen**: {len(scenes)} × {duration}s · **Tier**: {cveo.VEO_TIERS[tier]['label']} · "
            f"**Format**: {fmt['label']}\n"
            f"**Łączny czas wideo**: {len(scenes) * duration}s · **Veo total**: ${veo_cost_total:.2f}\n\n"
            f"**Krok 5** — dodać tło muzyczne (Lyria 3 podmiksowane pod całość, 30 s loop)?"
        ),
        actions=actions,
    ).send()


@cl.action_callback("lego_pick_music")
async def act_lego_pick_music(action):
    """Krok 5: muzyka wybrana → render N scen Veo + concat + opcjonalnie Lyria mix."""
    payload = action.payload or {}
    music_choice = payload.get("music") or action.value
    scenes = cl.user_session.get("lego_scenes") or []
    duration = int(cl.user_session.get("lego_duration") or 0)
    format_key = cl.user_session.get("lego_format")
    tier = cl.user_session.get("lego_tier") or cveo.VEO_DEFAULT_TIER
    if not scenes or format_key not in cveo.VEO_FORMATS or duration not in cveo.VEO_DURATIONS:
        await cl.Message(content="Sesja wygasła – odpal ponownie `/lego`.").send()
        return
    with_music = (music_choice == "yes")

    fmt = cveo.VEO_FORMATS[format_key]
    price_per_sec = cveo.VEO_TIERS[tier]["price_per_sec"]
    veo_cost_total = duration * price_per_sec * len(scenes)
    total_cost = veo_cost_total + (0.04 if with_music else 0.0)

    await cl.Message(
        content=(
            f"🧱 **Generuję {len(scenes)} {'scenę' if len(scenes)==1 else 'scen'} Lego ({cveo.VEO_TIERS[tier]['label']})…**\n\n"
            f"- **Format**: {fmt['label']} ({fmt['aspect_ratio']}) · **Długość/scena**: {duration}s\n"
            f"- **Tło**: {'Lyria 3 ✓' if with_music else 'brak'}\n"
            f"- **Łączny koszt**: ${total_cost:.2f}\n\n"
            f"Krok 1/3: enhancowanie promptów (Sonnet 4.6 × {len(scenes)} scen)…"
        ),
    ).send()

    # Enhance prompts sekwencyjnie (LLM calls są szybkie)
    enhanced_prompts: list[str] = []
    try:
        for i, scene in enumerate(scenes, 1):
            ep = await cl.make_async(cveo.enhance_prompt)(scene)
            enhanced_prompts.append(ep)
            await cl.Message(
                content=f"📝 **Prompt sceny {i}/{len(scenes)}** (EN):\n\n> {ep[:400]}{'...' if len(ep) > 400 else ''}",
            ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd enhancera promptu: `{type(e).__name__}: {e}`").send()
        return

    # Render każdej sceny przez Veo (sekwencyjnie – polling lock)
    await cl.Message(
        content=f"🎬 **Krok 2/3: render {len(scenes)} klipów Veo {tier}** (~2-3 min/klip)…",
    ).send()
    paths: list = []
    try:
        for i, ep in enumerate(enhanced_prompts, 1):
            await cl.Message(content=f"  ↻ Scena {i}/{len(scenes)}…").send()
            p = await cl.make_async(cveo.render_lego_video)(
                final_prompt=ep,
                format_key=format_key,
                duration=duration,
                tier=tier,
            )
            paths.append(p)
            await cl.Message(content=f"  ✓ Scena {i}/{len(scenes)}: `{p.name}`").send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd renderu Veo: `{type(e).__name__}: {e}`").send()
        return

    # Concat jeśli >1 scena
    if len(paths) > 1:
        await cl.Message(content=f"🪢 **Krok 3/3: łączę {len(paths)} klipów (`ffmpeg concat`)…**").send()
        try:
            import pathlib as _pl
            import datetime as _dt
            concat_out = paths[0].parent / f"lego_{tier}_{format_key}_concat_{_dt.datetime.now():%Y%m%d_%H%M%S}.mp4"
            final_path = await cl.make_async(cveo.concat_videos)(paths, concat_out)
        except Exception as e:
            await cl.Message(content=f"❌ Błąd concat: `{type(e).__name__}: {e}`. Wysyłam scenę 1.").send()
            final_path = paths[0]
    else:
        final_path = paths[0]

    # Opcjonalna muzyka pod całość
    if with_music:
        await cl.Message(content=f"🎹 **Generuję tło muzyczne (Lyria 3 Clip, $0,04)…**").send()
        try:
            combined_scenes_text = " | ".join(scenes)
            mixed_path, music_info = await cl.make_async(caud.add_music_to_video)(
                video_path=final_path,
                scene_or_script=combined_scenes_text,
            )
            final_path = mixed_path
            await cl.Message(
                content=(
                    f"🎶 **Tło dodane.**\n\n"
                    f"> {music_info['music_prompt'][:300]}{'...' if len(music_info['music_prompt']) > 300 else ''}"
                ),
            ).send()
        except Exception as e:
            await cl.Message(
                content=f"⚠️ Tło muzyczne nie udało się ({type(e).__name__}: {e}). Wysyłam bez muzyki.",
            ).send()

    cl.user_session.set("last_video_path", str(final_path))
    await cl.Message(
        content=(
            f"✅ **Lego wideo gotowe.**\n\n"
            f"- Scen: {len(scenes)} × {duration}s = **{len(scenes) * duration}s** total\n"
            f"- Tier: {cveo.VEO_TIERS[tier]['label']} · Format: {fmt['label']}\n"
            f"- Łączny koszt: ${total_cost:.2f}\n"
            f"- Plik: `{final_path.name}`\n\n"
            f"_`/tekst <olka|kaska|marta> <nowy tekst>` żeby podmienić ścieżkę audio._"
        ),
        elements=[cl.Video(path=str(final_path), name=final_path.name, display="inline")],
    ).send()
    cl.user_session.set("lego_scenes", None)
    cl.user_session.set("lego_format", None)
    cl.user_session.set("lego_duration", None)
    cl.user_session.set("lego_tier", None)


@cl.action_callback("img_format")
async def act_img_format(action):
    """Wybór formatu grafiki → generacja przez Nano Banana 2 + logo Actio overlay."""
    payload = action.payload or {}
    fmt_key = payload.get("format") or action.value
    topic = payload.get("topic") or cl.user_session.get("pending_image_topic")
    if not topic:
        await cl.Message(content="Brak tematu – uruchom ponownie `/grafika <temat>`.").send()
        return

    fmt = cig.FORMATS.get(fmt_key)
    if not fmt:
        await cl.Message(content=f"Nieznany format: {fmt_key}").send()
        return

    thinking = await cl.Message(
        content=(
            f"🎨 Generuję grafikę…\n\n"
            f"- **Temat**: {topic}\n"
            f"- **Format**: {fmt['label']} ({fmt['width']}×{fmt['height']})\n"
            f"- **Model**: Nano Banana 2 (Gemini 3 Pro Image)\n\n"
            f"_Trwa zwykle 30-90 sekund._"
        ),
    ).send()

    try:
        path = await cl.make_async(cig.generate_social_image)(topic, fmt_key)
    except Exception as e:
        await cl.Message(content=f"❌ Błąd generacji: `{type(e).__name__}: {e}`").send()
        return

    await cl.Message(
        content=(
            f"✅ Gotowe.\n\n"
            f"**Temat**: {topic}\n"
            f"**Format**: {fmt['label']} ({fmt['width']}×{fmt['height']}, {fmt['use_case']})"
        ),
        elements=[cl.Image(path=str(path), name=path.name, display="inline")],
    ).send()
    cl.user_session.set("pending_image_topic", None)


@cl.action_callback("export_csv")
async def act_export_csv(action):
    table = action.payload.get("table", "")
    days = _days()
    csv_buf = io.StringIO()
    name = "export.csv"
    try:
        if table == "campaigns":
            df = db.fetch_ads_campaigns(DB_PATH, days=days)
            name = f"ads-campaigns-{days}d.csv"
        elif table == "keywords":
            df = db.fetch_ads_keywords(DB_PATH, days=days)
            name = f"ads-keywords-{days}d.csv"
        elif table == "search_terms":
            df = db.fetch_ads_search_terms(DB_PATH, days=days, top=500)
            name = f"ads-search-terms-{days}d.csv"
        elif table == "gsc_queries":
            df = db.fetch_gsc_top_queries(DB_PATH, days=days, top=500)
            name = f"gsc-queries-{days}d.csv"
        elif table == "gsc_pages":
            df = db.fetch_gsc_top_pages(DB_PATH, days=days, top=500)
            name = f"gsc-pages-{days}d.csv"
        elif table == "landing_conversions":
            df = db.fetch_landing_conversions(DB_PATH, days=days, top=500)
            name = f"landing-conversions-{days}d.csv"
        else:
            await cl.Message(content="❌ Nieznana tabela").send()
            return
        df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue().encode("utf-8")
        await cl.Message(
            content=f"✅ CSV gotowy ({len(df)} wierszy)",
            elements=[cl.File(name=name, content=csv_bytes, mime="text/csv")],
        ).send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd: `{type(e).__name__}: {e}`").send()


# ── Renderery ─────────────────────────────────────────────────────────────────

async def _render_dashboard():
    days = _days()
    elements = []

    # Chart 1: Leady per dzień (z landing_conversions, sumy per dzień+source)
    try:
        landing = db.fetch_landing_conversions(DB_PATH, days=days, top=1000)
        if not landing.empty:
            # Trzeba zrobić per dzień. fetch_landing_conversions agreguje per landing×source bez daty.
            # Pobierzmy raw dziennie via direct SQL
            import sqlite3
            with sqlite3.connect(DB_PATH) as conn:
                df_daily = pd.read_sql_query(
                    """SELECT date, source_medium, SUM(event_count) AS leads
                       FROM landing_conversions
                       WHERE date >= date('now', ?)
                       GROUP BY date, source_medium
                       ORDER BY date""",
                    conn, params=[f"-{int(days)} days"],
                )
            if not df_daily.empty:
                fig = px.line(df_daily, x="date", y="leads", color="source_medium",
                              title=f"Leady per dzień ({days}d)", markers=True)
                fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
                elements.append(cl.Plotly(name="leads_chart", figure=fig, display="inline"))
    except Exception as e:
        elements.append(cl.Text(name="leads_err", content=f"Wykres leadów: błąd `{e}`"))

    # Chart 2: Lost IS per kampania (trend dzienny)
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            df_lost = pd.read_sql_query(
                """SELECT date, campaign_name,
                          AVG(rank_lost_is) * 100 AS lost_rank_pct
                   FROM ads_campaign_daily
                   WHERE date >= date('now', ?) AND status = 'ENABLED'
                   GROUP BY date, campaign_name
                   ORDER BY date""",
                conn, params=[f"-{int(days)} days"],
            )
        if not df_lost.empty:
            fig2 = px.line(df_lost, x="date", y="lost_rank_pct", color="campaign_name",
                           title=f"Lost IS (Rank) per kampania ({days}d) — niższe = lepiej",
                           markers=True)
            fig2.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10),
                               yaxis_title="Lost Rank %")
            elements.append(cl.Plotly(name="lost_is", figure=fig2, display="inline"))
    except Exception as e:
        elements.append(cl.Text(name="lost_is_err", content=f"Wykres Lost IS: błąd `{e}`"))

    # Chart 3: GSC pozycje top stron (top 10 stron z największą liczbą imp)
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            top_pages = pd.read_sql_query(
                """SELECT page FROM gsc_daily
                   WHERE date >= date('now', ?)
                   GROUP BY page ORDER BY SUM(impressions) DESC LIMIT 10""",
                conn, params=[f"-{int(days)} days"],
            )
            if not top_pages.empty:
                placeholders = ",".join("?" * len(top_pages))
                params = [f"-{int(days)} days"] + top_pages["page"].tolist()
                df_pos = pd.read_sql_query(
                    f"""SELECT date, page, AVG(position) AS avg_position
                        FROM gsc_daily
                        WHERE date >= date('now', ?) AND page IN ({placeholders})
                        GROUP BY date, page
                        ORDER BY date""",
                    conn, params=params,
                )
                # Skróć URL do labeli
                df_pos["page_short"] = df_pos["page"].str.replace("https://actio.pl", "", regex=False).str[:40]
                fig3 = px.line(df_pos, x="date", y="avg_position", color="page_short",
                               title=f"GSC pozycje top 10 stron ({days}d) — niższe = lepiej",
                               markers=True)
                fig3.update_yaxes(autorange="reversed")
                fig3.update_layout(height=400, margin=dict(l=10, r=10, t=40, b=10),
                                   yaxis_title="Średnia pozycja")
                elements.append(cl.Plotly(name="gsc_positions", figure=fig3, display="inline"))
    except Exception as e:
        elements.append(cl.Text(name="gsc_err", content=f"Wykres GSC: błąd `{e}`"))

    actions = [
        cl.Action(name="export_csv", value="campaigns", label="📥 CSV: kampanie",
                  payload={"table": "campaigns"}),
        cl.Action(name="export_csv", value="search_terms", label="📥 CSV: search terms",
                  payload={"table": "search_terms"}),
        cl.Action(name="export_csv", value="gsc_queries", label="📥 CSV: GSC queries",
                  payload={"table": "gsc_queries"}),
        cl.Action(name="export_csv", value="landing_conversions", label="📥 CSV: leady per landing",
                  payload={"table": "landing_conversions"}),
        cl.Action(name="dashboard", value="dashboard", label="🔄 Odśwież", payload={}),
    ]
    await cl.Message(
        content=f"## 📊 Dashboard ({days} dni)",
        elements=elements,
        actions=actions,
    ).send()


async def _render_reports_list():
    p = pathlib.Path(MD_REPORTS_DIR)
    if not p.exists() or not any(p.iterdir()):
        await cl.Message(content="### 📄 Raporty\n\n_Brak raportów. Wygeneruj pierwszy w menu._").send()
        await _show_menu()
        return
    files = sorted(p.glob("*.md"), reverse=True)[:30]
    actions = [
        cl.Action(name="view_report", value=f.name, label=f.stem, payload={"file": f.name})
        for f in files
    ]
    await cl.Message(
        content=f"### 📄 Raporty (ostatnie {len(files)})\n\nKliknij żeby zobaczyć.",
        actions=actions,
    ).send()


async def _render_alerts_feed():
    df = db.fetch_recent_alerts(DB_PATH, limit=20)
    if df.empty:
        await cl.Message(content="### 🚨 Alerty\n\n_Brak alertów w historii._").send()
        await _show_menu()
        return
    # Render z buttonami "resolve" dla nierozwiązanych
    lines = []
    actions = []
    for _, r in df.iterrows():
        emoji = "✅" if r["resolved"] else "🔴"
        lines.append(f"{emoji} **#{r['id']}** · {r['triggered_at']} · `{r['type']}`{' · '+str(r['campaign']) if r['campaign'] else ''}\n   {r['message']}")
        if not r["resolved"]:
            actions.append(cl.Action(name="resolve_alert", value=str(r["id"]),
                                     label=f"✓ Resolve #{r['id']}",
                                     payload={"id": int(r["id"])}))
    await cl.Message(
        content=f"### 🚨 Alerty (ostatnie {len(df)})\n\n" + "\n\n".join(lines),
        actions=actions[:10],  # limit żeby UI było czytelne
    ).send()


# ── LLM tool calling (Chat mode) ──────────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_history",
            "description": "GA4 — sesje, użytkownicy, konwersje per source/medium z ostatnich N dni",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "source_medium": {"type": "string", "description": "opcjonalny filtr np. 'google / cpc'"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_landing_conversions",
            "description": "GA4 — leady (generate_lead) zagregowane per landing × source/medium za N dni",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "top": {"type": "integer", "default": 30},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ads_campaigns",
            "description": "Google Ads — kampanie (klik/koszt/konw/CPA + Lost IS) za N dni. Pokazuje wszystkie aktywne kampanie.",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ads_keywords",
            "description": "Google Ads — top keywordy z QS i CPA za N dni. Filtr opcjonalny.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "keyword_filter": {"type": "string", "description": "fragment tekstu do dopasowania"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ads_search_terms",
            "description": "Google Ads — realne zapytania użytkowników za N dni (top wg kosztu)",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "top": {"type": "integer", "default": 20},
                    "term_filter": {"type": "string", "description": "fragment tekstu"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_gsc",
            "description": "Google Search Console — top queries lub pages organic z ostatnich N dni",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "group_by": {"type": "string", "enum": ["query", "page"], "default": "query"},
                    "top": {"type": "integer", "default": 20},
                    "filter_text": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "live_account_state",
            "description": "Aktualny live state konta Google Ads (kampanie z budżetami + lista negatywów per kampania) — bezpośrednio z API. Używaj zawsze gdy user pyta 'jakie mamy negatywy', 'jakie aktywne kampanie' itp.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _execute_tool(name: str, args: dict) -> str:
    """Wykonaj tool i zwróć wynik jako string (markdown table)."""
    try:
        if name == "query_history":
            df = db.fetch_history(DB_PATH, days=int(args.get("days", 7)),
                                  source_medium=args.get("source_medium"))
        elif name == "query_landing_conversions":
            df = db.fetch_landing_conversions(DB_PATH, days=int(args.get("days", 7)),
                                              top=int(args.get("top", 30)))
        elif name == "query_ads_campaigns":
            df = db.fetch_ads_campaigns(DB_PATH, days=int(args.get("days", 7)))
        elif name == "query_ads_keywords":
            df = db.fetch_ads_keywords(DB_PATH, days=int(args.get("days", 7)),
                                       keyword_filter=args.get("keyword_filter"))
            df = df.head(50)
        elif name == "query_ads_search_terms":
            df = db.fetch_ads_search_terms(DB_PATH, days=int(args.get("days", 7)),
                                           top=int(args.get("top", 20)),
                                           term_filter=args.get("term_filter"))
        elif name == "query_gsc":
            group_by = args.get("group_by", "query")
            top = int(args.get("top", 20))
            days = int(args.get("days", 7))
            ft = args.get("filter_text")
            if group_by == "page":
                df = db.fetch_gsc_top_pages(DB_PATH, days=days, top=top, filter_text=ft)
            else:
                df = db.fetch_gsc_top_queries(DB_PATH, days=days, top=top, filter_text=ft)
        elif name == "live_account_state":
            import ads
            cust = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")
            return ads.fetch_live_account_state(cust)
        else:
            return f"(unknown tool: {name})"

        if df.empty:
            return "(brak danych)"
        return df.to_markdown(index=False)
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


SYSTEM_PROMPT = """Jesteś asystentem marketingowym dla Actio (B2B VoIP).

Masz dostęp do bazy danych marketingowych: GA4, Google Search Console, Google Ads (kampanie / keywordy / search terms / Lost IS / live state). Odpowiadaj po polsku, krótko, konkretnie. Używaj tools żeby pobrać dane PRZED odpowiedzią.

Zasady:
- Gdy user pyta o coś bieżącego (negatywy, kampanie, budżety), używaj `live_account_state` (źródło prawdy z API).
- Gdy user pyta o historyczne metryki, używaj odpowiednich `query_*` tools.
- Po pobraniu danych odpowiadaj zwięźle z konkretnymi liczbami i interpretacją.
- Nigdy nie wymyślaj liczb bez wywołania tool.
- Język: polski, format markdown, krótkie tabelki gdy sensowne.
"""


async def _llm_chat(user_msg: str) -> str:
    if not OPENROUTER_KEY:
        return "❌ Brak OPENROUTER_API_KEY w env."

    from langfuse.openai import AsyncOpenAI
    client = AsyncOpenAI(
        api_key=OPENROUTER_KEY,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://actio.pl",
            "X-Title": "Actio Marketing CMO-layer",
        },
        timeout=120.0,
    )

    history = cl.user_session.get("chat_history") or []
    history.append({"role": "user", "content": user_msg})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    session_id = cl.user_session.get("id") or "anonymous"

    for _ in range(8):  # max 8 tool-call iterations
        resp = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            extra_body={"provider": {"data_collection": "deny"}},
            name="chainlit_chat",
            metadata={
                "source": "app.py",
                "use_case": "interactive_panel",
                "session_id": str(session_id),
            },
        )
        msg = resp.choices[0].message.model_dump(exclude_none=True)
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            final = msg.get("content") or "(brak odpowiedzi)"
            history.append({"role": "assistant", "content": final})
            cl.user_session.set("chat_history", history[-20:])  # cap kontekst
            return final

        for tc in tool_calls:
            fn = tc["function"]["name"]
            args = json.loads(tc["function"].get("arguments") or "{}")
            result = _execute_tool(fn, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result[:8000],  # cap żeby nie eksplodować kontekstu
            })

    return "(przekroczono limit iteracji tool calls)"


# ── on_message router ─────────────────────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    raw_text = (message.content or "").strip()
    text = raw_text.lower()

    # ─── Multi-scene scene collection state machine ──────────────────────────
    # Jeśli user jest w trakcie podawania opisów scen, każdą wiadomość traktuj jako
    # opis kolejnej sceny. Po zebraniu N → wyświetl menu (tier / avatar). Komendy
    # "/" przerywają state.
    # ─── Eleven scenariusz collection (single paste) ─────────────────────
    if cl.user_session.get("awaiting_eleven_scenariusz") and raw_text and not text.startswith("/"):
        cl.user_session.set("awaiting_eleven_scenariusz", None)
        await cl.Message(content=f"🔍 **Parsuję scenariusz dla Seedance 2.0 (Sonnet 4.6)…**").send()
        try:
            scenes = await cl.make_async(celeven.parse_scenario_via_llm)(raw_text)
        except Exception as e:
            await cl.Message(content=f"❌ Parser failed: `{type(e).__name__}: {e}`. Wklej scenariusz ponownie po `/eleven`.").send()
            return
        cl.user_session.set("eleven_scenes", scenes)

        # Pokaż preview – sceny + szacunkowy koszt (dla obu tierów)
        total_s = sum(int(s["duration_s"]) for s in scenes)
        chars_total = sum(len(s["voiceover"]) for s in scenes)
        std_cost = total_s * celeven.SEEDANCE_TIERS["standard"]["price_per_sec"]
        fast_cost = total_s * celeven.SEEDANCE_TIERS["fast"]["price_per_sec"]
        tts_cost = chars_total * 0.0001

        # Seedance max 15s per scena – flaguj jeśli scena dłuższa
        warnings = []
        for i, s in enumerate(scenes, 1):
            d = int(s["duration_s"])
            if d < celeven.SEEDANCE_MIN_DURATION:
                warnings.append(f"⚠️ Scena {i}: {d}s < {celeven.SEEDANCE_MIN_DURATION}s (Seedance min) – wymuszam {celeven.SEEDANCE_MIN_DURATION}s")
            elif d > celeven.SEEDANCE_MAX_DURATION:
                warnings.append(f"⚠️ Scena {i}: {d}s > {celeven.SEEDANCE_MAX_DURATION}s (Seedance max) – wymuszam {celeven.SEEDANCE_MAX_DURATION}s")

        preview_lines = []
        for i, s in enumerate(scenes, 1):
            d = max(celeven.SEEDANCE_MIN_DURATION, min(celeven.SEEDANCE_MAX_DURATION, int(s["duration_s"])))
            preview_lines.append(
                f"**Scena {i}** ({d}s)\n"
                f"  🎬 {s['image'][:120]}{'...' if len(s['image']) > 120 else ''}\n"
                f"  🎙 {s['voiceover'][:120]}{'...' if len(s['voiceover']) > 120 else ''}"
            )
        preview = "\n\n".join(preview_lines)

        actions = [
            cl.Action(name="eleven_pick_tier", value=tier_key,
                      label=t["label"], payload={"tier": tier_key})
            for tier_key, t in celeven.SEEDANCE_TIERS.items()
        ]
        warn_block = ("\n" + "\n".join(warnings) + "\n") if warnings else ""
        await cl.Message(
            content=(
                f"✅ **Sparsowane {len(scenes)} scen, ~{total_s}s łącznie.**\n\n"
                f"{preview}\n{warn_block}\n"
                f"**Koszty szacowane**:\n"
                f"- Seedance Standard: **${std_cost:.2f}** · Fast: **${fast_cost:.2f}**\n"
                f"- ElevenLabs Riley: {chars_total} znaków ≈ **${tts_cost:.2f}**\n\n"
                f"**Krok 1/4** — wybierz tier Seedance:"
            ),
            actions=actions,
        ).send()
        return

    # ─── Reklama scenariusz collection (single paste) ──────────────────────
    if cl.user_session.get("awaiting_reklama_scenariusz") and raw_text and not text.startswith("/"):
        cl.user_session.set("awaiting_reklama_scenariusz", None)
        await cl.Message(content=f"🔍 **Parsuję scenariusz (Sonnet 4.6)…**").send()
        try:
            scenes = await cl.make_async(creklama.parse_scenario_via_llm)(raw_text)
        except Exception as e:
            await cl.Message(content=f"❌ Parser failed: `{type(e).__name__}: {e}`. Wklej scenariusz ponownie po `/reklama`.").send()
            return
        cl.user_session.set("reklama_scenes", scenes)

        # Preview + cost estimate
        chunk_total = sum(len(creklama.split_to_veo_chunks(s["duration_s"])) for s in scenes)
        total_s = sum(s["duration_s"] for s in scenes)
        chunk_seconds_total = sum(sum(creklama.split_to_veo_chunks(s["duration_s"])) for s in scenes)
        veo_cost = chunk_seconds_total * cveo.VEO_TIERS["lite"]["price_per_sec"]
        chars_total = sum(len(s["voiceover"]) for s in scenes)
        tts_cost = chars_total * 0.0001  # ElevenLabs PRO ≈ $0.0001/char

        preview_lines = []
        for i, s in enumerate(scenes, 1):
            chunks = creklama.split_to_veo_chunks(s["duration_s"])
            preview_lines.append(
                f"**Scena {i}** ({s['duration_s']}s, chunki Veo: {'+'.join(map(str, chunks))})\n"
                f"  🎬 {s['image'][:120]}{'...' if len(s['image']) > 120 else ''}\n"
                f"  🎙 {s['voiceover'][:120]}{'...' if len(s['voiceover']) > 120 else ''}"
            )
        preview = "\n\n".join(preview_lines)

        actions = [
            cl.Action(name="reklama_pick_speed", value=str(spd),
                      label=f"{spd}×{label}",
                      payload={"speed": spd})
            for spd, label in [(0.85, " (wolniej)"), (1.0, " (normalnie)"), (1.1, " (lekko szybciej)"), (1.2, " (szybciej)")]
        ]
        await cl.Message(
            content=(
                f"✅ **Sparsowane {len(scenes)} scen, {total_s}s łącznie.**\n\n"
                f"{preview}\n\n"
                f"**Koszty szacowane** (Veo Lite – hardcoded):\n"
                f"- Veo: {chunk_total} klipów × łącznie {chunk_seconds_total}s = **${veo_cost:.2f}**\n"
                f"- ElevenLabs Maria: {chars_total} znaków ≈ **${tts_cost:.2f}**\n"
                f"- Łącznie bez muzyki: **${veo_cost + tts_cost:.2f}**\n\n"
                f"**Krok 1/3** — wybierz tempo lektora ElevenLabs Maria:"
            ),
            actions=actions,
        ).send()
        return

    awaiting = cl.user_session.get("awaiting_scenes_for")
    if awaiting and raw_text and not text.startswith("/"):
        count = int(cl.user_session.get("awaiting_scene_count") or 0)
        if awaiting == "lego":
            scenes = cl.user_session.get("lego_scenes") or []
            scenes.append(raw_text)
            cl.user_session.set("lego_scenes", scenes)
            if len(scenes) < count:
                await cl.Message(content=f"**Scena {len(scenes)+1}/{count}** – opisz scenę:").send()
            else:
                cl.user_session.set("awaiting_scenes_for", None)
                cl.user_session.set("awaiting_scene_count", None)
                summary = "\n".join(f"  {i+1}. {s[:80]}{'...' if len(s) > 80 else ''}" for i, s in enumerate(scenes))
                actions = [
                    cl.Action(name="lego_pick_tier", value=tier_key, label=t["label"],
                              payload={"tier": tier_key})
                    for tier_key, t in cveo.VEO_TIERS.items()
                ]
                await cl.Message(
                    content=(
                        f"✅ Zebrane {len(scenes)} {'scena' if len(scenes)==1 else 'scen'} Lego:\n{summary}\n\n"
                        f"**Krok 2** — jakość Veo (Lite/Fast/Standard):\n\n"
                        f"_Lite (default) = 8× tańszy. Standard = max fidelity._"
                    ),
                    actions=actions,
                ).send()
            return
        if awaiting == "kasia":
            scenes = cl.user_session.get("kasia_scenes") or []
            scenes.append(raw_text)
            cl.user_session.set("kasia_scenes", scenes)
            if len(scenes) < count:
                await cl.Message(content=f"**Scena {len(scenes)+1}/{count}** – opisz co Kasia robi/o czym mówi:").send()
            else:
                cl.user_session.set("awaiting_scenes_for", None)
                cl.user_session.set("awaiting_scene_count", None)
                summary = "\n".join(f"  {i+1}. {s[:80]}{'...' if len(s) > 80 else ''}" for i, s in enumerate(scenes))
                actions = [
                    cl.Action(name="kasia_pick_tier", value=tier_key, label=t["label"],
                              payload={"tier": tier_key})
                    for tier_key, t in cveo.VEO_TIERS.items()
                ]
                await cl.Message(
                    content=(
                        f"✅ Zebrane {len(scenes)} {'scena' if len(scenes)==1 else 'scen'} Kasi:\n{summary}\n\n"
                        f"**Krok 2** — jakość Veo (Lite/Fast/Standard):\n\n"
                        f"_Lite (default) = 8× tańszy. Standard = max fidelity twarzy/mimiki._"
                    ),
                    actions=actions,
                ).send()
            return
        if awaiting in ("scenariusz", "dialog"):
            dialog_mode = (awaiting == "dialog")
            scenes = cl.user_session.get("video_scenes") or []
            scenes.append(raw_text)
            cl.user_session.set("video_scenes", scenes)
            if len(scenes) < count:
                prompt = (
                    f"**Scena {len(scenes)+1}/{count}** – wklej dokładny tekst do wypowiedzenia:"
                    if dialog_mode
                    else f"**Scena {len(scenes)+1}/{count}** – podaj temat sceny:"
                )
                await cl.Message(content=prompt).send()
            else:
                cl.user_session.set("awaiting_scenes_for", None)
                cl.user_session.set("awaiting_scene_count", None)
                summary = "\n".join(f"  {i+1}. {s[:80]}{'...' if len(s) > 80 else ''}" for i, s in enumerate(scenes))
                actions = [
                    cl.Action(name="video_pick_avatar", value=key, label=a["label"],
                              payload={"avatar": key})
                    for key, a in cvg.AVATARS.items()
                ]
                mode_label = "Dialog (1:1)" if dialog_mode else "Scenariusz (LLM)"
                await cl.Message(
                    content=(
                        f"✅ Zebrane {len(scenes)} {'scena' if len(scenes)==1 else 'scen'} ({mode_label}):\n{summary}\n\n"
                        f"**Krok 2** — wybierz awatara:"
                    ),
                    actions=actions,
                ).send()
            return
    # Komenda "/" w trakcie zbierania scen anuluje stan
    if awaiting and text.startswith("/"):
        cl.user_session.set("awaiting_scenes_for", None)
        cl.user_session.set("awaiting_scene_count", None)

    # /dialog – multi-scene HeyGen z gotowymi dialogami 1:1 (bez LLM)
    if text == "/dialog" or text.startswith("/dialog "):
        cl.user_session.set("video_scenes", [])
        cl.user_session.set("video_dialog_mode", True)
        cl.user_session.set("video_avatar", None)
        cl.user_session.set("video_voice", None)
        cl.user_session.set("video_format", None)
        actions = [
            cl.Action(name="video_pick_scene_count", value=str(n),
                      label=f"{n} {'scena' if n == 1 else 'sceny' if n < 5 else 'scen'}",
                      payload={"count": n, "dialog_mode": True})
            for n in range(1, 6)
        ]
        await cl.Message(
            content=(
                "🎤 **Dialog (HeyGen Kaśka, 1:1)** — ile scen?\n\n"
                "Każda scena = jeden render HeyGen z Twoim tekstem 1:1 (bez LLM). "
                "Łączymy przez `ffmpeg concat` w jeden mp4.\n\n"
                "Koszt per scena: ~$0,30 (HeyGen, do ~250 słów ≈ 90 s).\n"
                "Przykład: 3 sceny × 60 s ≈ 3 min wideo, **koszt ~$0,90**.\n\n"
                "_Po wyborze liczby scen poproszę o dokładny tekst do wypowiedzenia w każdej._"
            ),
            actions=actions,
        ).send()
        return

    # /film – menu z 4 trybami generowania wideo
    if text == "/film" or text.startswith("/film "):
        actions = [
            cl.Action(name="film_menu_scenariusz", value="scenariusz",
                      label="Scenariusz (HeyGen LLM)", payload={}),
            cl.Action(name="film_menu_dialog", value="dialog",
                      label="Dialog (HeyGen 1:1)", payload={}),
            cl.Action(name="film_menu_lego", value="lego",
                      label="Lego (Veo brick)", payload={}),
            cl.Action(name="film_menu_kasia", value="kasia",
                      label="Kasia (Veo Actio)", payload={}),
            cl.Action(name="film_menu_reklama", value="reklama",
                      label="Reklama (timeline + lektor)", payload={}),
        ]
        await cl.Message(
            content=(
                "**Generator wideo Actio – 4 tryby (multi-scene)**\n\n"
                "Każdy tryb pyta o liczbę scen (1–5). Łączymy ffmpeg concat. "
                "Opcjonalne tło muzyczne (Lyria 3, +$0,04).\n\n"
                "**Scenariusz** – `/scenariusz` · HeyGen Kasia + LLM script ~90 s · ~$0,30/scena\n\n"
                "**Dialog** – `/dialog` · HeyGen Kasia + Twój tekst 1:1 · ~$0,30/scena\n\n"
                "**Lego** – `/lego` · Veo 3.1 brick-style 4/6/8 s · Lite=$0,05/s · Fast=$0,10/s · Std=$0,40/s\n\n"
                "**Kasia** – `/kasia` · Veo + natywny audio · pracowniczka biura Actio, doradca B2B\n"
                "Koszt 8 s Lite: $0,40/scena\n\n"
                "**Reklama** – `/reklama` · Veo Lite B-roll + voice-over ElevenLabs Maria\n"
                "Wklejasz scenariusz (timeline + lektor), LLM parsuje. Auto-split scen >8 s. Wybór tempa.\n"
                "Koszt 60 s reklamy: ~$3,00 (Veo) + $0,12 (Maria) ≈ $3,12\n\n"
                "**Eleven** – `/eleven` · Seedance 2.0 (fal.ai) + Riley voice (ElevenLabs)\n"
                "Wklejasz scenariusz, wybierasz tier (Standard/Fast) + aspect (6 opcji) + duration 4-15s/scena.\n"
                "Wymaga FAL_KEY. Koszt 60 s: ~$18 (standard) lub ~$15 (fast)\n\n"
                "**Tekst** – `/tekst <głos> <nowy tekst>` · ElevenLabs PL: olka/kaska/marta · ~$0,01"
            ),
            actions=actions,
        ).send()
        return

    # /scenariusz – multi-scene HeyGen z LLM-pisanymi skryptami (Kaśka avatar)
    if text == "/scenariusz" or text.startswith("/scenariusz "):
        cl.user_session.set("video_scenes", [])
        cl.user_session.set("video_dialog_mode", False)
        cl.user_session.set("video_avatar", None)
        cl.user_session.set("video_voice", None)
        cl.user_session.set("video_format", None)
        actions = [
            cl.Action(name="video_pick_scene_count", value=str(n),
                      label=f"{n} {'scena' if n == 1 else 'sceny' if n < 5 else 'scen'}",
                      payload={"count": n, "dialog_mode": False})
            for n in range(1, 6)
        ]
        await cl.Message(
            content=(
                "📝 **Scenariusz (HeyGen Kaśka, LLM)** — ile scen?\n\n"
                "Dla każdej sceny podasz **temat**, a LLM (Sonnet 4.6) sam napisze skrypt ~90 s. "
                "Łączymy renderem `ffmpeg concat`.\n\n"
                "Koszt per scena: ~$0,30 (HeyGen) + ~$0,01 LLM.\n"
                "Przykład: 3 sceny ≈ 4-5 min wideo, **koszt ~$0,93**.\n\n"
                "_Po wyborze liczby scen poproszę o temat każdej po kolei._"
            ),
            actions=actions,
        ).send()
        return

    # /eleven – Seedance 2.0 via fal.ai + ElevenLabs Riley voice overlay
    if text == "/eleven" or text.startswith("/eleven "):
        if not os.environ.get("FAL_KEY"):
            await cl.Message(
                content=(
                    "⚠️ **FAL_KEY nie ustawiony**\n\n"
                    "`/eleven` używa fal.ai (Seedance 2.0). Potrzebujesz klucza fal.ai:\n"
                    "1. `fal.ai` → Sign up / Login\n"
                    "2. Dashboard → API Keys → Create new\n"
                    "3. Top up balance (min $5 – Seedance ~$1-4 per clip)\n"
                    "4. Wklej mi klucz (`fal_xxxxxxxx`) w czacie\n\n"
                    "Po dodaniu klucza odpal `/eleven` ponownie."
                ),
            ).send()
            return
        cl.user_session.set("eleven_scenes", None)
        cl.user_session.set("eleven_tier", None)
        cl.user_session.set("eleven_aspect", None)
        cl.user_session.set("awaiting_eleven_scenariusz", True)
        await cl.Message(
            content=(
                "🎥 **Eleven (Seedance 2.0 via fal.ai + ElevenLabs Riley)**\n\n"
                "Wklej w następnej wiadomości pełen scenariusz w formacie:\n"
                "- Timeline `0:00-0:12` + opis sceny + `Lektor: ...`\n"
                "- LUB blok `[12s]` + opis + `LEKTOR: ...`\n\n"
                "**Stack**: Seedance 2.0 (text-to-video, 720p, native audio off) → ElevenLabs Riley TTS overlay → concat.\n"
                "**Limity Seedance**: duration 4-15 s na scenę, 6 aspect ratios (21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16).\n\n"
                "Po sparsowaniu wybierzesz: tier (Standard/Fast) → aspect ratio → muzyka."
            ),
        ).send()
        return

    # /reklama – strukturalny scenariusz z timeline + voice-over (Veo Lite hardcoded)
    if text == "/reklama" or text.startswith("/reklama "):
        cl.user_session.set("reklama_scenes", None)
        cl.user_session.set("reklama_speed", None)
        cl.user_session.set("reklama_format", None)
        cl.user_session.set("awaiting_reklama_scenariusz", True)
        await cl.Message(
            content=(
                "📺 **Reklama (Veo Lite B-roll + voice-over ElevenLabs Maria)**\n\n"
                "Wklej w następnej wiadomości pełen scenariusz w dowolnym formacie – LLM (Sonnet 4.6) sparsuje "
                "na sceny z timestampami, opisem obrazu i tekstem lektora.\n\n"
                "Akceptowane formaty (LLM jest elastyczny):\n"
                "- Timeline `0:00-0:12 [opis] / Lektor: [text]`\n"
                "- Wiersze tabeli\n"
                "- Bloki tekstowe z `[12s]` + `LEKTOR:`\n\n"
                "Pipeline: parser → preview → tempo lektora → format → muzyka → render.\n\n"
                "**Veo Lite** ($0,05/s) hardcoded. Auto-split scen >8 s na chunki 4/6/8 s.\n"
                "Voice-over ElevenLabs Maria zastępuje natywny Veo audio."
            ),
        ).send()
        return

    # /kasia – multi-scene Veo 3.1 z Kasią (pracowniczka biura Actio, doradca biznesowy)
    if text == "/kasia" or text.startswith("/kasia "):
        cl.user_session.set("kasia_scenes", [])
        cl.user_session.set("kasia_format", None)
        cl.user_session.set("kasia_duration", None)
        cl.user_session.set("kasia_tier", None)
        actions = [
            cl.Action(name="kasia_pick_scene_count", value=str(n),
                      label=f"{n} {'scena' if n == 1 else 'sceny' if n < 5 else 'scen'}",
                      payload={"count": n})
            for n in range(1, 6)
        ]
        await cl.Message(
            content=(
                "👩‍💼 **Kasia (Veo 3.1)** — ile scen?\n\n"
                "Kasia to pracowniczka biura Actio, doradca biznesowy B2B. Veo renderuje sceny "
                "z natywnym audio PL. Klipy łączymy `ffmpeg concat`.\n\n"
                "⚠️ **Veo limit 8 s/scena**. Dla dłuższych scen (np. 12 s) trzeba podzielić.\n"
                "⚠️ **Spójność postaci** między scenami przybliżona – Veo image input nie działa, polegamy na detail w prompcie.\n\n"
                "Koszty per scena Lite (8 s): **$0,40 Veo**.\n"
                "Przykład: 3 sceny × 8 s = 24 s, **koszt $1,20** (+ $0,04 muzyka).\n\n"
                "_Po wyborze liczby scen poproszę o opis każdej._"
            ),
            actions=actions,
        ).send()
        return

    # /lego – multi-scene Veo 3.1 (brick-style animation)
    if text == "/lego" or text.startswith("/lego "):
        cl.user_session.set("lego_scenes", [])
        cl.user_session.set("lego_format", None)
        cl.user_session.set("lego_duration", None)
        actions = [
            cl.Action(name="lego_pick_scene_count", value=str(n),
                      label=f"{n} {'scena' if n == 1 else 'sceny' if n < 5 else 'scen'}",
                      payload={"count": n})
            for n in range(1, 6)
        ]
        await cl.Message(
            content=(
                "🎬 **Lego (Veo 3.1)** — ile scen wygenerować?\n\n"
                "Każda scena to osobny klip Veo (4 / 6 / 8 s). Łączymy je przez `ffmpeg concat` w jeden mp4.\n\n"
                "Koszty per scena (Veo): 4 s = $1,60 · 6 s = $2,40 · 8 s = $3,20.\n"
                "Przykład: 3 sceny × 8 s = **24 s wideo, koszt $9,60** (+ $0,04 jeśli muzyka).\n\n"
                "_Po wyborze liczby scen poproszę o opis każdej po kolei._"
            ),
            actions=actions,
        ).send()
        return

    # /tekst <olka|kaska|marta> <text> – podmień ścieżkę audio ostatniego wideo (ElevenLabs TTS)
    if text.startswith("/tekst"):
        args = raw_text[len("/tekst"):].strip()
        parts = args.split(maxsplit=1)
        last_video = cl.user_session.get("last_video_path")
        if not last_video or not os.path.exists(last_video):
            await cl.Message(
                content=(
                    "Nie znalazłem ostatniego filmu w sesji.\n\n"
                    "Wygeneruj najpierw film przez `/film` (menu → Scenariusz/Dialog/Lego) – potem `/tekst` "
                    "zastąpi w nim ścieżkę audio nową syntezą."
                ),
            ).send()
            return
        if len(parts) < 2 or parts[0].lower() not in caud.VOICES_EL:
            voices_list = " · ".join(f"`{k}` ({v['label']})" for k, v in caud.VOICES_EL.items())
            await cl.Message(
                content=(
                    "**Podmień ścieżkę audio (ElevenLabs TTS)**\n\n"
                    f"Użycie: `/tekst <głos> <nowy tekst>`\n"
                    f"Dostępne głosy: {voices_list}\n\n"
                    f"Przykład: `/tekst kaska Cześć, tu Actio. Wirtualny numer firmowy aktywujesz w 24 godziny.`\n\n"
                    f"Operuje na ostatnim wygenerowanym filmie (Veo/HeyGen). `-shortest` ucina audio do długości wideo, "
                    f"więc trzymaj się długości oryginalnego filmu (8 s ≈ 22 słów PL)."
                ),
            ).send()
            return
        voice_key = parts[0].lower()
        new_text = parts[1].strip()
        if not new_text:
            await cl.Message(content="Brak tekstu po wyborze głosu.").send()
            return

        await cl.Message(
            content=(
                f"🎤 **Podmieniam ścieżkę audio…**\n\n"
                f"- Wideo: `{os.path.basename(last_video)}`\n"
                f"- Głos: **{caud.VOICES_EL[voice_key]['label']}**\n"
                f"- Tekst ({len(new_text)} znaków): {new_text[:200]}{'...' if len(new_text) > 200 else ''}"
            ),
        ).send()

        try:
            output_path, info = await cl.make_async(caud.overlay_voice_on_video)(
                video_path=last_video,
                text=new_text,
                voice_key=voice_key,
            )
        except Exception as e:
            await cl.Message(content=f"❌ Błąd podmiany audio: `{type(e).__name__}: {e}`").send()
            return

        cl.user_session.set("last_video_path", str(output_path))
        await cl.Message(
            content=(
                f"✅ **Audio podmienione.**\n\n"
                f"- Głos: {info['voice_label']}\n"
                f"- Tekst: {info['char_count']} znaków · MP3: {info['audio_bytes']//1024} KB\n"
                f"- Plik: `{output_path.name}`"
            ),
            elements=[cl.Video(path=str(output_path), name=output_path.name, display="inline")],
        ).send()
        return

    # /grafika <temat> – generator grafik social-media (Nano Banana 2 + logo Actio)
    if text.startswith("/grafika"):
        topic = raw_text[len("/grafika"):].strip()
        if not topic:
            await cl.Message(
                content=(
                    "**Generator grafik social media**\n\n"
                    "Użycie: `/grafika <temat>`\n"
                    "Przykład: `/grafika wirtualny numer telefonu dla firm`\n\n"
                    "Po podaniu tematu wybierzesz format (kwadrat / pion / poziom)."
                ),
            ).send()
            return

        cl.user_session.set("pending_image_topic", topic)
        actions = [
            cl.Action(
                name="img_format",
                value=key,
                label=f"{f['label']} ({f['width']}×{f['height']})",
                payload={"format": key, "topic": topic},
            )
            for key, f in cig.FORMATS.items()
        ]
        await cl.Message(
            content=(
                f"**Temat**: {topic}\n\n"
                f"Wybierz format grafiki:"
            ),
            actions=actions,
        ).send()
        return

    # Komendy globalne
    if text in ("menu", "/menu", "wstecz", "back"):
        await _show_menu()
        return

    if text in ("dashboard", "wykresy", "wykres"):
        _set_mode("dashboard")
        await _render_dashboard()
        return

    if text in ("raporty", "raport list", "lista raportów"):
        _set_mode("reports")
        await _render_reports_list()
        return

    if text in ("alerty", "alerts"):
        _set_mode("alerts")
        await _render_alerts_feed()
        return

    if text in ("wygeneruj raport", "generuj raport", "raport teraz"):
        await act_generate_report(None)
        return

    # Tryb chat — Sonnet 4.6 z tool calling
    if _mode() == "chat":
        thinking = await cl.Message(content="🤔 Myślę...").send()
        try:
            answer = await _llm_chat(message.content or "")
        except Exception as e:
            answer = f"❌ Błąd LLM: `{type(e).__name__}: {e}`"
        await cl.Message(content=answer).send()
        return

    # Domyślnie: skieruj do menu z pytaniem
    await cl.Message(
        content=(
            f"Napisałeś: **{message.content}**\n\n"
            "Aby zadać pytanie asystentowi, wybierz **💬 Chat** z menu poniżej. "
            "Albo użyj przycisków szybkich akcji."
        ),
    ).send()
    await _show_menu()
