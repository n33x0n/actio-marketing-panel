"""MCP stdio server — narzędzia do synchronizacji GA4 i queryowania historii."""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

import ads
import analyze
import db
import ga4
import gsc


mcp = FastMCP("actio-marketing")

DB_PATH = os.environ.get("DB_PATH", "marketing_data.db")
GA4_PROPERTY_ID = os.environ.get("GA4_PROPERTY_ID", "")
ADS_CUSTOMER_ID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")


@mcp.tool()
def sync_ga4_data() -> str:
    """Pobiera ostatnie 7 dni danych z GA4 (sessions / users / conversions
    per date × sessionSourceMedium) i zapisuje do lokalnej bazy SQLite.
    Idempotent — istniejące dni są aktualizowane, starsze zachowane.
    """
    try:
        if not GA4_PROPERTY_ID:
            return "ERROR: brak zmiennej środowiskowej GA4_PROPERTY_ID"
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return "ERROR: brak zmiennej środowiskowej GOOGLE_APPLICATION_CREDENTIALS"

        db.init_db(DB_PATH)
        rows = ga4.fetch_last_7_days(GA4_PROPERTY_ID)
        if not rows:
            return "GA4 zwróciło 0 wierszy dla ostatnich 7 dni."

        count = db.upsert_rows(DB_PATH, rows)
        dates = sorted({r["date"] for r in rows})
        return f"Zsynchronizowano {count} wierszy ({dates[0]} → {dates[-1]})."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def query_history(days: int = 30, source_medium: str | None = None) -> str:
    """Przeszukuje lokalną historię konwersji w SQLite.

    Args:
        days: ile ostatnich dni uwzględnić (default 30).
        source_medium: opcjonalny filtr po źródle/medium (np. "google / cpc").
    """
    try:
        db.init_db(DB_PATH)
        df = db.fetch_history(DB_PATH, days=days, source_medium=source_medium)
        if df.empty:
            return (
                "Brak danych w bazie dla podanych kryteriów. "
                "Uruchom najpierw `sync_ga4_data` żeby zasilić bazę z GA4."
            )
        return df.to_markdown(index=False)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def sync_gsc_data() -> str:
    """Pobiera ostatnie 7 dni danych z Google Search Console (date × query × page)
    dla wszystkich property do których SA ma dostęp. Idempotent upsert do SQLite.
    Uwzględnia 3-dniowy lag GSC (końcowy zakres = today - 3).
    """
    try:
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return "ERROR: brak zmiennej środowiskowej GOOGLE_APPLICATION_CREDENTIALS"

        db.init_db(DB_PATH)
        rows, sites = gsc.fetch_all_sites_last_7_days()
        if not sites:
            return "ERROR: SA nie ma dostępu do żadnej property w GSC."
        if not rows:
            return f"GSC zwróciło 0 wierszy dla {len(sites)} property: {', '.join(sites)}."

        count = db.upsert_gsc_rows(DB_PATH, rows)
        dates = sorted({r["date"] for r in rows})
        return (
            f"Zsynchronizowano {count} wierszy GSC ({dates[0]} → {dates[-1]}) "
            f"z {len(sites)} property: {', '.join(sites)}."
        )
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def query_gsc(
    days: int = 30,
    group_by: str = "query",
    filter_text: str | None = None,
    top: int = 20,
) -> str:
    """Top zapytań (query) lub stron (page) z Google Search Console.

    Args:
        days: ile ostatnich dni uwzględnić (default 30).
        group_by: "query" (domyślne) albo "page" — po czym grupować agregaty.
        filter_text: opcjonalny fragment tekstu do LIKE — filtruje query lub page.
        top: ile top wyników zwrócić (default 20).
    """
    try:
        db.init_db(DB_PATH)
        if group_by == "page":
            df = db.fetch_gsc_top_pages(DB_PATH, days=days, top=top, filter_text=filter_text)
        else:
            df = db.fetch_gsc_top_queries(DB_PATH, days=days, top=top, filter_text=filter_text)
        if df.empty:
            return (
                "Brak danych GSC w bazie dla podanych kryteriów. "
                "Uruchom najpierw `sync_gsc_data`."
            )
        return df.to_markdown(index=False)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def sync_ads_data() -> str:
    """Pobiera ostatnie 7 dni metryk kampanii Google Ads (date × campaign)
    z konta `GOOGLE_ADS_CUSTOMER_ID` i upserts do SQLite.
    """
    try:
        if not ADS_CUSTOMER_ID:
            return "ERROR: brak GOOGLE_ADS_CUSTOMER_ID"
        for var in ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_OAUTH_CLIENT_ID",
                    "GOOGLE_ADS_OAUTH_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                    "GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
            if not os.environ.get(var):
                return f"ERROR: brak {var}"

        db.init_db(DB_PATH)
        rows = ads.fetch_campaigns_last_7_days(ADS_CUSTOMER_ID)
        if not rows:
            return "Google Ads zwróciło 0 wierszy dla ostatnich 7 dni."
        count = db.upsert_ads_campaign_rows(DB_PATH, rows)
        dates = sorted({r["date"] for r in rows})
        return f"Zsynchronizowano {count} wierszy Ads ({dates[0]} → {dates[-1]})."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def query_ads_campaigns(days: int = 7, campaign_filter: str | None = None) -> str:
    """Agregat per kampania za ostatnie N dni (clicks/impr/cost/conv/CTR/CPC/CPA).

    Args:
        days: ile dni wstecz (default 7).
        campaign_filter: opcjonalny LIKE na campaign_name.
    """
    try:
        db.init_db(DB_PATH)
        df = db.fetch_ads_campaigns(DB_PATH, days=days, campaign_filter=campaign_filter)
        if df.empty:
            return "Brak danych Ads w bazie. Uruchom najpierw `sync_ads_data`."
        return df.to_markdown(index=False)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def sync_ads_keywords() -> str:
    """Pobiera ostatnie 30 dni metryk słów kluczowych Google Ads
    (date × campaign × ad_group × keyword) z Quality Score.
    """
    try:
        if not ADS_CUSTOMER_ID:
            return "ERROR: brak GOOGLE_ADS_CUSTOMER_ID"
        db.init_db(DB_PATH)
        rows = ads.fetch_keywords_last_30_days(ADS_CUSTOMER_ID)
        if not rows:
            return "Google Ads zwróciło 0 słów kluczowych dla ostatnich 30 dni."
        count = db.upsert_ads_keyword_rows(DB_PATH, rows)
        dates = sorted({r["date"] for r in rows})
        return f"Zsynchronizowano {count} wierszy keywords ({dates[0]} → {dates[-1]})."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def query_ads_keywords(days: int = 30, keyword_filter: str | None = None) -> str:
    """Agregat per keyword za ostatnie N dni (clicks/impr/cost/conv/QS/CTR/CPC/CPA).

    Args:
        days: ile dni wstecz (default 30).
        keyword_filter: opcjonalny LIKE na keyword.
    """
    try:
        db.init_db(DB_PATH)
        df = db.fetch_ads_keywords(DB_PATH, days=days, keyword_filter=keyword_filter)
        if df.empty:
            return "Brak danych keywords. Uruchom najpierw `sync_ads_keywords`."
        return df.to_markdown(index=False)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def sync_ads_search_terms() -> str:
    """Pobiera realne frazy wyszukiwania, po których Google pokazuje reklamy
    (search_term_view) — ostatnie 30 dni.
    """
    try:
        if not ADS_CUSTOMER_ID:
            return "ERROR: brak GOOGLE_ADS_CUSTOMER_ID"
        db.init_db(DB_PATH)
        rows = ads.fetch_search_terms_last_30_days(ADS_CUSTOMER_ID)
        if not rows:
            return "Google Ads zwróciło 0 search terms dla ostatnich 30 dni."
        count = db.upsert_ads_search_term_rows(DB_PATH, rows)
        dates = sorted({r["date"] for r in rows})
        return f"Zsynchronizowano {count} wierszy search terms ({dates[0]} → {dates[-1]})."
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def query_ads_search_terms(
    days: int = 30,
    term_filter: str | None = None,
    top: int = 50,
) -> str:
    """Top realnych fraz wyszukiwania, po których wyświetlane były reklamy.

    Args:
        days: ile dni wstecz (default 30).
        term_filter: opcjonalny LIKE na search_term.
        top: ile wyników (default 50).
    """
    try:
        db.init_db(DB_PATH)
        df = db.fetch_ads_search_terms(DB_PATH, days=days, term_filter=term_filter, top=top)
        if df.empty:
            return "Brak danych search terms. Uruchom najpierw `sync_ads_search_terms`."
        return df.to_markdown(index=False)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


@mcp.tool()
def generate_report() -> str:
    """CMO-layer: fresh sync wszystkich źródeł (GA4 / GSC / Ads × 3) + analiza
    Opus 4.7 przez OpenRouter. Zapisuje raport do Obsidiana i wysyła push przez Pushover.
    Zwraca treść raportu markdown.
    """
    try:
        result = analyze.generate_report()
        return (
            f"### Raport Actio Marketing — {result['date']}\n\n"
            f"Zapisany w Obsidianie: `{result['vault_path']}`\n\n"
            f"---\n\n{result['report_md']}"
        )
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


if __name__ == "__main__":
    mcp.run()
