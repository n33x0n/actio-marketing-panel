"""Chainlit — panel do przeglądu historii konwersji."""
from __future__ import annotations

import os
import re

import chainlit as cl
import plotly.express as px

import analyze
import db


DB_PATH = os.environ.get("DB_PATH", "marketing_data.db")

WELCOME = (
    "### Panel Actio Marketing\n\n"
    "**GA4 — konwersje**\n"
    "- **pokaż historię** — ostatnie 30 dni\n"
    "- **pokaż historię 7 dni** / **pokaż historię 60**\n"
    "- **pokaż historię google / cpc** — filtr po źródle/medium\n\n"
    "**GSC — SEO (zapytania i strony z Google)**\n"
    "- **pokaż zapytania** — top 20 organic queries (domyślnie 30 dni)\n"
    "- **pokaż zapytania 7 dni**\n"
    "- **pokaż strony** — top 20 stron lądowania z Google\n\n"
    "**Google Ads**\n"
    "- **pokaż kampanie** — agregat per kampania (default 7 dni)\n"
    "- **pokaż keywords** / **pokaż słowa kluczowe** — top słów kluczowych z QS\n"
    "- **pokaż search terms** / **pokaż frazy** — realne frazy z wyszukiwarki\n\n"
    "Dane zasilają narzędzia MCP `sync_ga4_data`, `sync_gsc_data`, `sync_ads_data`, "
    "`sync_ads_keywords`, `sync_ads_search_terms` w Claude Code.\n\n"
    "**CMO-layer (analiza Opus 4.7)**\n"
    "- **wygeneruj raport** / **raport** — fresh sync wszystkich źródeł + analiza LLM "
    "(zapis do Obsidiana + push na telefon)."
)


def _parse_days(text: str) -> int:
    match = re.search(r"\b(\d{1,3})\b", text)
    return int(match.group(1)) if match else 30


def _parse_source(text: str) -> str | None:
    match = re.search(r"([a-z0-9\.\-_]+\s*/\s*[a-z0-9\.\-_]+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


@cl.on_chat_start
async def start() -> None:
    db.init_db(DB_PATH)
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def handle(msg: cl.Message) -> None:
    text = msg.content.strip().lower()

    if "raport" in text or "wygeneruj" in text:
        await _handle_report()
        return
    if "histori" in text:
        await _handle_history(text)
        return
    if "kampani" in text or "campaign" in text:
        await _handle_ads_campaigns(text)
        return
    if "keyword" in text or "słowa kluczow" in text or "slowa kluczow" in text:
        await _handle_ads_keywords(text)
        return
    if "search term" in text or "fraz" in text:
        await _handle_ads_search_terms(text)
        return
    if "zapytan" in text or "quer" in text:
        await _handle_gsc_queries(text)
        return
    if "stron" in text or "page" in text:
        await _handle_gsc_pages(text)
        return

    await cl.Message(content=WELCOME).send()


async def _handle_report() -> None:
    msg = cl.Message(content="Generuję raport — fresh sync + analiza Opus 4.7. Może chwilę potrwać...")
    await msg.send()
    try:
        result = await cl.make_async(analyze.generate_report)()
    except Exception as e:
        await cl.Message(content=f"**Błąd**: `{type(e).__name__}: {e}`").send()
        return

    sync_lines = "\n".join(f"- **{k}**: {v}" for k, v in result["sync_status"].items())
    header = (
        f"### Raport Actio Marketing — {result['date']}\n\n"
        f"**Sync status**\n{sync_lines}\n\n"
        f"**Zapisany w Obsidianie**: `{result['vault_path']}`\n\n"
        f"---\n\n"
    )
    await cl.Message(content=header + result["report_md"]).send()


async def _handle_ads_campaigns(text: str) -> None:
    days = _parse_days(text) if re.search(r"\b\d{1,3}\b", text) else 7
    df = db.fetch_ads_campaigns(DB_PATH, days=days)
    if df.empty:
        await cl.Message(content=(
            f"Brak danych Ads dla **{days} dni**.\n\n"
            "Uruchom `sync_ads_data` w Claude Code."
        )).send()
        return

    fig = px.bar(
        df.head(10),
        x="campaign_name",
        y="cost_pln",
        hover_data=["clicks", "impressions", "conversions", "ctr_pct", "avg_cpc", "cpa"],
        title=f"Wydatki per kampania — {days} dni",
    )
    fig.update_layout(xaxis_title="Kampania", yaxis_title="Koszt (PLN)")

    header = f"### Kampanie Google Ads ({days} dni)\n\n"
    await cl.Message(
        content=header + df.to_markdown(index=False),
        elements=[cl.Plotly(name="ads_campaigns", figure=fig, display="inline")],
    ).send()


async def _handle_ads_keywords(text: str) -> None:
    days = _parse_days(text)
    df = db.fetch_ads_keywords(DB_PATH, days=days)
    if df.empty:
        await cl.Message(content=(
            f"Brak danych keywords dla **{days} dni**.\n\n"
            "Uruchom `sync_ads_keywords` w Claude Code."
        )).send()
        return

    top = df.head(20)
    fig = px.bar(
        top,
        x="keyword",
        y="cost_pln",
        hover_data=["clicks", "impressions", "conversions", "avg_qs", "ctr_pct", "avg_cpc", "cpa"],
        title=f"Top 20 słów kluczowych po koszcie — {days} dni",
    )
    fig.update_layout(xaxis_title="Słowo kluczowe", yaxis_title="Koszt (PLN)")

    header = f"### Słowa kluczowe Google Ads ({days} dni, {len(df)} wierszy)\n\n"
    await cl.Message(
        content=header + top.to_markdown(index=False),
        elements=[cl.Plotly(name="ads_keywords", figure=fig, display="inline")],
    ).send()


async def _handle_ads_search_terms(text: str) -> None:
    days = _parse_days(text)
    df = db.fetch_ads_search_terms(DB_PATH, days=days, top=50)
    if df.empty:
        await cl.Message(content=(
            f"Brak danych search terms dla **{days} dni**.\n\n"
            "Uruchom `sync_ads_search_terms` w Claude Code."
        )).send()
        return

    top = df.head(20)
    fig = px.bar(
        top,
        x="search_term",
        y="cost_pln",
        hover_data=["clicks", "impressions", "conversions", "ctr_pct", "avg_cpc"],
        title=f"Top 20 realnych fraz po koszcie — {days} dni",
    )
    fig.update_layout(xaxis_title="Fraza", yaxis_title="Koszt (PLN)")

    header = f"### Search terms Google Ads ({days} dni, {len(df)} wierszy)\n\n"
    await cl.Message(
        content=header + top.to_markdown(index=False),
        elements=[cl.Plotly(name="ads_search_terms", figure=fig, display="inline")],
    ).send()


async def _handle_history(text: str) -> None:
    days = _parse_days(text)
    source_medium = _parse_source(text)

    df = db.fetch_history(DB_PATH, days=days, source_medium=source_medium)
    if df.empty:
        suffix = f" (źródło: `{source_medium}`)" if source_medium else ""
        await cl.Message(content=(
            f"Brak danych dla ostatnich **{days} dni**{suffix}.\n\n"
            "Uruchom `sync_ga4_data` w Claude Code żeby zasilić bazę z GA4."
        )).send()
        return

    trend = df.groupby("date", as_index=False)["conversions"].sum()
    title = f"Trend konwersji — ostatnie {days} dni"
    if source_medium:
        title += f" ({source_medium})"

    fig = px.line(trend, x="date", y="conversions", markers=True, title=title)
    fig.update_layout(xaxis_title="Data", yaxis_title="Konwersje")

    header = f"### Historia ({len(df)} wierszy, {days} dni"
    if source_medium:
        header += f", źródło: `{source_medium}`"
    header += ")\n\n"

    await cl.Message(
        content=header + df.to_markdown(index=False),
        elements=[cl.Plotly(name="trend", figure=fig, display="inline")],
    ).send()


async def _handle_gsc_queries(text: str) -> None:
    days = _parse_days(text)
    df = db.fetch_gsc_top_queries(DB_PATH, days=days, top=20)
    if df.empty:
        await cl.Message(content=(
            f"Brak danych GSC dla ostatnich **{days} dni**.\n\n"
            "Uruchom `sync_gsc_data` w Claude Code żeby zasilić bazę z Search Console."
        )).send()
        return

    top10 = df.head(10)
    fig = px.bar(
        top10,
        x="query",
        y="clicks",
        hover_data=["impressions", "ctr_pct", "avg_position"],
        title=f"Top 10 zapytań organic — {days} dni",
    )
    fig.update_layout(xaxis_title="Zapytanie", yaxis_title="Kliki")

    header = f"### Top {len(df)} zapytań organic ({days} dni)\n\n"
    await cl.Message(
        content=header + df.to_markdown(index=False),
        elements=[cl.Plotly(name="gsc_queries", figure=fig, display="inline")],
    ).send()


async def _handle_gsc_pages(text: str) -> None:
    days = _parse_days(text)
    df = db.fetch_gsc_top_pages(DB_PATH, days=days, top=20)
    if df.empty:
        await cl.Message(content=(
            f"Brak danych GSC dla ostatnich **{days} dni**.\n\n"
            "Uruchom `sync_gsc_data` w Claude Code żeby zasilić bazę z Search Console."
        )).send()
        return

    top10 = df.head(10)
    fig = px.bar(
        top10,
        x="page",
        y="clicks",
        hover_data=["impressions", "ctr_pct", "avg_position"],
        title=f"Top 10 stron organic — {days} dni",
    )
    fig.update_layout(xaxis_title="Strona", yaxis_title="Kliki")

    header = f"### Top {len(df)} stron organic ({days} dni)\n\n"
    await cl.Message(
        content=header + df.to_markdown(index=False),
        elements=[cl.Plotly(name="gsc_pages", figure=fig, display="inline")],
    ).send()
