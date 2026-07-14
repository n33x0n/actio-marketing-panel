"""GEO / AI Share of Voice – raport trendu.

Czyta tabele geo_visibility (z geo_monitor.py), buduje raport:
- macierz zapytanie x silnik (czy Actio wymienione) dla ostatniego pomiaru,
- KPI AI Share of Voice: ostatni vs poprzedni pomiar + delta,
- top konkurenci,
- KPI brandu z GSC: pozycja frazy 'actio' (i 'actio voip'),
- ruch z AI-referrerow w GA4 (chatgpt.com, perplexity.ai itd.).

Bialy kapelusz: tylko raport widocznosci. Uruchamiac na Mikrusie (tam DB + creds).
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from datetime import date, timedelta

from brand_config import get_brand

BASE_DIR = pathlib.Path(__file__).resolve().parent
AI_REFERRERS = ("chatgpt", "openai", "perplexity", "gemini", "copilot", "claude", "grok", "x.ai")
# Rozbudowany rozkład AI-leadów (typ konwersji + landing + strona-konwersji). Flaga = łatwy rollback.
AI_LEADS_DETAIL = True


def _env(key: str, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    try:
        cfg = json.loads((BASE_DIR / ".mcp.json").read_text())
        return cfg["mcpServers"]["actio-marketing"]["env"].get(key, default)
    except Exception:
        return default


def _load_run(conn: sqlite3.Connection, run_date: str) -> list[dict]:
    cur = conn.execute(
        "SELECT query, engine, actio_mentioned, actio_rank, competitors FROM geo_visibility WHERE run_date=?",
        (run_date,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _sov(rows: list[dict]) -> float:
    return round(sum(r["actio_mentioned"] for r in rows) / len(rows), 3) if rows else 0.0


def geo_section(conn: sqlite3.Connection) -> list[str]:
    try:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM geo_visibility ORDER BY run_date DESC").fetchall()]
    except sqlite3.OperationalError:
        return ["_AI Share of Voice: brak pomiaru dla tej marki (uruchom geo_monitor)._"]
    if not dates:
        return ["_AI Share of Voice: brak danych (uruchom geo_monitor)._"]
    latest = _load_run(conn, dates[0])
    prev = _load_run(conn, dates[1]) if len(dates) > 1 else []
    out = []
    sov_l = _sov(latest)
    line = f"**AI Share of Voice: {sov_l*100:.0f}%** ({dates[0]})"
    if prev:
        sov_p = _sov(prev)
        d = (sov_l - sov_p) * 100
        line += f"  | poprzednio {sov_p*100:.0f}% ({dates[1]})  | delta {d:+.0f} pp"
    else:
        line += "  | (baseline – brak poprzedniego pomiaru)"
    out.append(line)

    engines = sorted({r["engine"] for r in latest})
    queries = []
    for r in latest:
        if r["query"] not in queries:
            queries.append(r["query"])
    out.append("")
    out.append("| zapytanie | " + " | ".join(engines) + " |")
    out.append("|" + "---|" * (len(engines) + 1))
    for q in queries:
        cells = []
        for e in engines:
            rec = next((r for r in latest if r["query"] == q and r["engine"] == e), None)
            cells.append("✓" if rec and rec["actio_mentioned"] else "✗")
        out.append(f"| {q[:42]} | " + " | ".join(cells) + " |")

    # top konkurenci w ostatnim pomiarze
    comp: dict[str, int] = {}
    for r in latest:
        for c in json.loads(r["competitors"] or "[]"):
            comp[c] = comp.get(c, 0) + 1
    top = sorted(comp.items(), key=lambda x: -x[1])[:8]
    out.append("")
    out.append("Top konkurenci (wzmianki / " + str(len(latest)) + " odpowiedzi): " +
               ", ".join(f"{k} {v}" for k, v in top))
    return out


def gsc_brand() -> list[str]:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        path = _env("GOOGLE_APPLICATION_CREDENTIALS")
        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        end = date.today() - timedelta(days=3)
        start = end - timedelta(days=28)
        resp = svc.searchanalytics().query(siteUrl=get_brand().gsc_property, body={
            "startDate": str(start), "endDate": str(end), "dimensions": ["query"],
            "dimensionFilterGroups": [{"filters": [
                {"dimension": "query", "operator": "contains", "expression": get_brand().brand_query}]}],
            "rowLimit": 10,
        }).execute()
        rows = resp.get("rows", [])
        out = [f"GSC brand (28 dni, do {end}):"]
        for r in rows[:6]:
            out.append(f"  - '{r['keys'][0]}': poz {r['position']:.1f}, impr {int(r['impressions'])}, klik {int(r['clicks'])}")
        if not rows:
            out.append(f"  (brak fraz z '{get_brand().brand_query}')")
        return out
    except Exception as e:
        return [f"GSC brand: blad ({type(e).__name__}: {e})"]


def ga4_ai_referrers() -> list[str]:
    try:
        gac = _env("GOOGLE_APPLICATION_CREDENTIALS")
        if gac:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gac
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import RunReportRequest, Dimension, Metric, DateRange
        prop = _env("GA4_PROPERTY_ID", get_brand().ga4_property_default)
        cl = BetaAnalyticsDataClient()
        req = RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="sessionSource")],
            metrics=[Metric(name="sessions")],
            date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
        )
        resp = cl.run_report(req)
        sessions: dict[str, int] = {}
        for row in resp.rows:
            src = row.dimension_values[0].value
            if any(k in src.lower() for k in AI_REFERRERS):
                sessions[src] = sessions.get(src, 0) + int(row.metric_values[0].value)

        # leady (generate_lead) per zrodlo sesji
        from google.analytics.data_v1beta.types import Filter, FilterExpression
        req_leads = RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="sessionSource")],
            metrics=[Metric(name="eventCount")],
            date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
            dimension_filter=FilterExpression(filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(value=get_brand().lead_event),
            )),
        )
        leads: dict[str, int] = {}
        for row in cl.run_report(req_leads).rows:
            src = row.dimension_values[0].value
            if any(k in src.lower() for k in AI_REFERRERS):
                leads[src] = leads.get(src, 0) + int(row.metric_values[0].value)

        srcs = sorted(set(sessions) | set(leads), key=lambda s: (-leads.get(s, 0), -sessions.get(s, 0)))
        out = ["**Ruch i leady z czatbotow AI (GA4, 30 dni):**", ""]
        if not srcs:
            out.append("0 sesji z chatgpt/claude/perplexity/gemini/copilot/grok (jeszcze nas tam nie ma / brak ruchu)")
            return out

        # --- rozbudowa: typ konwersji + landing + strona-konwersji per zrodlo ---
        by_type: dict[str, dict[str, int]] = {}   # src -> {lead_type: count}
        landing: dict[str, dict[str, int]] = {}    # src -> {path: sessions}
        conv_page: dict[str, dict[str, int]] = {}  # src -> {path: generate_lead}
        if AI_LEADS_DETAIL:
            lead_filter = FilterExpression(filter=Filter(
                field_name="eventName", string_filter=Filter.StringFilter(value=get_brand().lead_event)))

            def _agg(target, dim, metric, flt=None):
                try:
                    r = cl.run_report(RunReportRequest(
                        property=f"properties/{prop}",
                        dimensions=[Dimension(name="sessionSource"), Dimension(name=dim)],
                        metrics=[Metric(name=metric)],
                        date_ranges=[DateRange(start_date="30daysAgo", end_date="today")],
                        dimension_filter=flt,
                    ))
                    import re as _re
                    for row in r.rows:
                        src = row.dimension_values[0].value
                        if not any(k in src.lower() for k in AI_REFERRERS):
                            continue
                        key = row.dimension_values[1].value or "(nieznany)"
                        # zwin hash rejestracji do jednej sciezki (agregacja + czytelnosc)
                        key = _re.sub(r"(/registration_confirm/)[0-9a-f]{16,}", r"\1", key.split("?")[0])
                        n = int(row.metric_values[0].value)
                        target.setdefault(src, {})[key] = target.setdefault(src, {}).get(key, 0) + n
                except Exception:
                    pass  # brak custom dimension / za malo danych -> pomijamy detal

            _agg(by_type, "customEvent:lead_type", "eventCount", lead_filter)
            _agg(landing, "landingPagePlusQueryString", "sessions")
            _agg(conv_page, "pagePath", "eventCount", lead_filter)

        types = ("phone", "registration", "form")
        header = "| zrodlo | sesje | leady | telefon | rejestracja | formularz |" if AI_LEADS_DETAIL and by_type \
            else f"| zrodlo | sesje | leady ({get_brand().lead_event}) |"
        sep = "|---|---:|---:|---:|---:|---:|" if AI_LEADS_DETAIL and by_type else "|---|---:|---:|"
        out += [header, sep]
        tot_t = {t: 0 for t in types}
        for s in srcs:
            se, le = sessions.get(s, 0), leads.get(s, 0)
            if AI_LEADS_DETAIL and by_type:
                bt = by_type.get(s, {})
                vals = [bt.get(t, 0) for t in types]
                for t, v in zip(types, vals):
                    tot_t[t] += v
                out.append(f"| {s} | {se} | {le} | " + " | ".join(str(v) for v in vals) + " |")
            else:
                out.append(f"| {s} | {se} | {le} |")
        if AI_LEADS_DETAIL and by_type:
            out.append(f"| **razem** | **{sum(sessions.values())}** | **{sum(leads.values())}** | "
                       + " | ".join(f"**{tot_t[t]}**" for t in types) + " |")
        else:
            out.append(f"| **razem** | **{sum(sessions.values())}** | **{sum(leads.values())}** |")

        def _top(d: dict, s: str, n=3) -> str:
            items = sorted(d.get(s, {}).items(), key=lambda x: -x[1])[:n]
            return ", ".join(f"{p.split('?')[0]} ({c})" for p, c in items) if items else "–"

        if AI_LEADS_DETAIL and landing:
            out.append("")
            out.append("_Landing (gdzie ląduje ruch AI):_")
            for s in srcs:
                if landing.get(s):
                    out.append(f"- {s}: {_top(landing, s)}")
        if AI_LEADS_DETAIL and conv_page:
            out.append("")
            out.append("_Strona konwersji (gdzie odpala się generate_lead):_")
            for s in srcs:
                if conv_page.get(s):
                    out.append(f"- {s}: {_top(conv_page, s)}")
        return out
    except Exception as e:
        return [f"GA4 AI-referrers: blad ({type(e).__name__}: {e})"]


def ai_bots_section() -> list[str]:
    """Boty AI czytajace serwis: marki na Cloudflare -> CF Analytics (cloudflare.py);
    inaczej -> ai_bot_hits (ai_bot_report)."""
    if get_brand().cloudflare_enabled:
        try:
            import cloudflare
            sec = cloudflare.build_section()
            return sec.splitlines() if sec else []
        except Exception as e:
            return [f"Boty AI (CF): blad ({type(e).__name__})"]
    try:
        import ai_bot_report
        return ai_bot_report.build_section()
    except Exception as e:
        return [f"Boty AI: blad ({type(e).__name__})"]


def build_report(as_section: bool = False) -> str:
    """as_section=True -> naglowek H2 do wklejenia w wiekszy raport (mail CMO);
    False -> samodzielny raport z H1 (uruchomienie z CLI)."""
    db_path = _env("DB_PATH") or str(BASE_DIR / "marketing_data.db")
    conn = sqlite3.connect(db_path)
    header = "## GEO / AI Share of Voice" if as_section else f"# Raport GEO / AI Share of Voice – {date.today().isoformat()}"
    parts = [header, ""]
    parts += geo_section(conn)
    conn.close()
    parts += [""] + ai_bots_section()
    parts += [""] + gsc_brand()
    parts += [""] + ga4_ai_referrers()
    return "\n".join(parts)


if __name__ == "__main__":
    print(build_report())
