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
import httpx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import alerts
import analyze  # ładuje env z .mcp.json przy imporcie
import db


# ── Konfiguracja ──────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "marketing_data.db")
MD_REPORTS_DIR = os.environ.get("MD_REPORTS_DIR", "./md-reports")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAINLIT_CHAT_MODEL", "anthropic/claude-sonnet-4.6")

DEFAULT_DAYS = 30
DAYS_OPTIONS = [7, 14, 30, 60, 90, 180, 365]


# ── Helpery sesji ─────────────────────────────────────────────────────────────

def _days() -> int:
    return int(cl.user_session.get("days") or DEFAULT_DAYS)


def _set_mode(mode: str) -> None:
    cl.user_session.set("mode", mode)


def _mode() -> str:
    return cl.user_session.get("mode") or "menu"


# ── Banner alertów ────────────────────────────────────────────────────────────

async def _send_alert_banner() -> None:
    """Wysyła wiadomość z banner-em jeśli są nierozwiązane alerty."""
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


async def _show_menu(intro: str | None = None) -> None:
    _set_mode("menu")
    text = intro or "### Wybierz, co chcesz zobaczyć"
    text += f"\n\n_Aktualny zakres dat: **{_days()} dni** (zmień w Settings ⚙️ — ikona koła zębatego)_"
    await cl.Message(content=text, actions=MENU_ACTIONS).send()


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
    filename = action.payload.get("file", "")
    path = pathlib.Path(MD_REPORTS_DIR) / filename
    if not path.exists():
        await cl.Message(content=f"❌ Brak pliku `{filename}`").send()
    else:
        content = path.read_text(encoding="utf-8")
        await cl.Message(content=content).send()
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
            pdf_path = pathlib.Path("/tmp") / f"{filename.replace('.md', '.pdf')}"
            pdf_path.write_bytes(pdf_bytes)
            await cl.Message(
                content=f"✅ PDF gotowy: `{pdf_path.name}`",
                elements=[cl.File(name=pdf_path.name, path=str(pdf_path), display="inline")],
            ).send()
        except ImportError:
            await cl.Message(content="❌ WeasyPrint nie zainstalowany. `uv add weasyprint`").send()
    except Exception as e:
        await cl.Message(content=f"❌ Błąd: `{type(e).__name__}: {e}`").send()


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
        csv_path = pathlib.Path("/tmp") / name
        csv_path.write_text(csv_buf.getvalue(), encoding="utf-8")
        await cl.Message(
            content=f"✅ CSV gotowy ({len(df)} wierszy)",
            elements=[cl.File(name=name, path=str(csv_path), display="inline")],
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

    history = cl.user_session.get("chat_history") or []
    history.append({"role": "user", "content": user_msg})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    async with httpx.AsyncClient(timeout=120.0) as client:
        for _ in range(8):  # max 8 tool-call iterations
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={"model": CHAT_MODEL, "messages": messages, "tools": TOOLS_SCHEMA},
            )
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                final = msg.get("content", "(brak odpowiedzi)")
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
    text = (message.content or "").strip().lower()

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
