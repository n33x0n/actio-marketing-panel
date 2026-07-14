"""Cloudflare GraphQL Analytics — konektor dla raportu (marki na CF, np. sendly.link).

Warstwa 2 (AI Crawl Control): które boty AI czytają serwis, ile, jakie ścieżki.
Warstwa 3 (edge HTTP health): rozkład statusów, błędy 4xx/5xx, wolumen ruchu.

Źródło: zone-scoped httpRequestsAdaptiveGroups (GraphQL Analytics API).
Uwaga (plan Free): pojedyncze zapytanie max 1 dzień → pętla dzień po dniu.
Moduł samodzielny — trzyma własne tabele cf_* w tej samej bazie SQLite (DB_PATH),
bez zależności od db.py. Włączany per marka: brand_config.cloudflare_enabled.

Env: CLOUDFLARE_API_TOKEN (read-only: Account/Zone Analytics:Read), CLOUDFLARE_ZONE_ID.
"""
from __future__ import annotations

import datetime
import os
import sqlite3

import httpx

UTC = datetime.timezone.utc

GQL_URL = "https://api.cloudflare.com/client/v4/graphql"

# Substringi userAgent klasyfikujące boty AI (kolejność = priorytet dopasowania).
AI_BOTS: tuple[str, ...] = (
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "PerplexityBot",
    "Perplexity-User",
    "CCBot",
    "Google-Extended",
    "Bytespider",
    "Amazonbot",
    "Applebot",
    "meta-externalagent",
)


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Brak zmiennej środowiskowej: {name}")
    return val


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_env('CLOUDFLARE_API_TOKEN')}",
        "Content-Type": "application/json",
    }


def _gql(query: str) -> dict:
    r = httpx.post(GQL_URL, headers=_headers(), json={"query": query}, timeout=30.0)
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(f"Cloudflare GraphQL: {payload['errors']}")
    return payload["data"]


def _day_windows(days: int) -> list[tuple[str, str, str]]:
    """Zwraca [(from_iso, to_iso, date_str), ...] dla ostatnich `days` pełnych dni UTC.

    Każde okno = dokładnie 1 doba (wymóg planu Free CF). Pomija dzisiejszy (niepełny) dzień.
    """
    today = datetime.datetime.now(UTC).date()
    out: list[tuple[str, str, str]] = []
    for i in range(1, days + 1):
        d = today - datetime.timedelta(days=i)
        nxt = d + datetime.timedelta(days=1)
        out.append((f"{d}T00:00:00Z", f"{nxt}T00:00:00Z", d.isoformat()))
    return out


def _classify(user_agent: str) -> str | None:
    ua = user_agent.lower()
    for bot in AI_BOTS:
        if bot.lower() in ua:
            return bot
    return None


# --- tabele ---------------------------------------------------------------

def init_cf_tables(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS cf_http_status (
            date TEXT NOT NULL,
            status INTEGER NOT NULL,
            requests INTEGER NOT NULL,
            bytes INTEGER NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (date, status)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS cf_ai_crawlers (
            date TEXT NOT NULL,
            bot TEXT NOT NULL,
            path TEXT NOT NULL,
            requests INTEGER NOT NULL,
            bytes INTEGER NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (date, bot, path)
        )""")
        con.commit()
    finally:
        con.close()


def _upsert(db_path: str, table: str, cols: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    ph = ",".join("?" * len(cols))
    con = sqlite3.connect(db_path)
    try:
        con.executemany(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({ph})", rows)
        con.commit()
    finally:
        con.close()
    return len(rows)


# --- fetch ----------------------------------------------------------------

def fetch_http_status(zone_id: str, days: int = 7) -> list[dict]:
    """Rozkład statusów HTTP na brzegu, dzień po dniu."""
    out: list[dict] = []
    now = datetime.datetime.now(UTC).isoformat()
    for frm, to, date_str in _day_windows(days):
        q = (
            f'{{viewer{{zones(filter:{{zoneTag:"{zone_id}"}}){{'
            f'httpRequestsAdaptiveGroups(filter:{{datetime_geq:"{frm}",datetime_leq:"{to}"}},'
            f'limit:50,orderBy:[count_DESC]){{count dimensions{{edgeResponseStatus}} sum{{edgeResponseBytes}}}}'
            f'}}}}}}'
        )
        try:
            groups = _gql(q)["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]
        except Exception:
            continue  # brak danych/retencji dla tego dnia — pomijamy
        for g in groups:
            out.append({
                "date": date_str,
                "status": int(g["dimensions"]["edgeResponseStatus"]),
                "requests": int(g["count"]),
                "bytes": int(g["sum"]["edgeResponseBytes"]),
                "synced_at": now,
            })
    return out


def fetch_ai_crawlers(zone_id: str, days: int = 7) -> list[dict]:
    """Requesty botów AI (userAgent × ścieżka), dzień po dniu. Filtr OR = tylko boty AI."""
    ors = ",".join(f'{{userAgent_like:"%{b}%"}}' for b in AI_BOTS)
    out: list[dict] = []
    now = datetime.datetime.now(UTC).isoformat()
    for frm, to, date_str in _day_windows(days):
        q = (
            f'{{viewer{{zones(filter:{{zoneTag:"{zone_id}"}}){{'
            f'httpRequestsAdaptiveGroups(filter:{{datetime_geq:"{frm}",datetime_leq:"{to}",OR:[{ors}]}},'
            f'limit:500,orderBy:[count_DESC]){{count dimensions{{userAgent clientRequestPath}} sum{{edgeResponseBytes}}}}'
            f'}}}}}}'
        )
        try:
            groups = _gql(q)["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"]
        except Exception:
            continue
        # agreguj per (bot, path) — jeden userAgent moze miec kilka wariantow wersji
        agg: dict[tuple[str, str], list[int]] = {}
        for g in groups:
            bot = _classify(g["dimensions"]["userAgent"])
            if not bot:
                continue
            path = g["dimensions"]["clientRequestPath"] or "/"
            key = (bot, path)
            cur = agg.setdefault(key, [0, 0])
            cur[0] += int(g["count"])
            cur[1] += int(g["sum"]["edgeResponseBytes"])
        for (bot, path), (req, by) in agg.items():
            out.append({"date": date_str, "bot": bot, "path": path,
                        "requests": req, "bytes": by, "synced_at": now})
    return out


def sync_all(db_path: str, zone_id: str | None = None, days: int = 7) -> dict[str, str]:
    """Init + sync obu warstw do bazy. Zwraca status per warstwa (jak run_all_syncs)."""
    zone_id = zone_id or _env("CLOUDFLARE_ZONE_ID")
    init_cf_tables(db_path)
    results: dict[str, str] = {}
    try:
        rows = fetch_http_status(zone_id, days)
        n = _upsert(db_path, "cf_http_status",
                    ["date", "status", "requests", "bytes", "synced_at"],
                    [(r["date"], r["status"], r["requests"], r["bytes"], r["synced_at"]) for r in rows])
        results["cf_http_status"] = f"OK ({n} wierszy)"
    except Exception as e:
        results["cf_http_status"] = f"ERROR: {type(e).__name__}: {e}"
    try:
        rows = fetch_ai_crawlers(zone_id, days)
        n = _upsert(db_path, "cf_ai_crawlers",
                    ["date", "bot", "path", "requests", "bytes", "synced_at"],
                    [(r["date"], r["bot"], r["path"], r["requests"], r["bytes"], r["synced_at"]) for r in rows])
        results["cf_ai_crawlers"] = f"OK ({n} wierszy)"
    except Exception as e:
        results["cf_ai_crawlers"] = f"ERROR: {type(e).__name__}: {e}"
    return results


# --- sekcja do raportu ----------------------------------------------------

def build_section(db_path: str | None = None, days: int = 7) -> str:
    """Sekcja markdown „Cloudflare" (boty AI + zdrowie brzegu) z bazy. Pusta gdy brak danych."""
    db_path = db_path or _env("DB_PATH")
    con = sqlite3.connect(db_path)
    try:
        bots = con.execute(
            "SELECT bot, SUM(requests) FROM cf_ai_crawlers "
            "WHERE date >= date('now', ?) GROUP BY bot ORDER BY 2 DESC",
            (f"-{days} day",),
        ).fetchall()
        paths = con.execute(
            "SELECT path, SUM(requests) FROM cf_ai_crawlers "
            "WHERE date >= date('now', ?) GROUP BY path ORDER BY 2 DESC LIMIT 8",
            (f"-{days} day",),
        ).fetchall()
        status = con.execute(
            "SELECT status, SUM(requests) FROM cf_http_status "
            "WHERE date >= date('now', ?) GROUP BY status ORDER BY 2 DESC",
            (f"-{days} day",),
        ).fetchall()
    except sqlite3.OperationalError:
        return ""  # tabele nie istnieją / brak danych
    finally:
        con.close()

    if not bots and not status:
        return ""

    lines = ["## Cloudflare — ruch brzegowy i boty AI (7 dni)", ""]

    if bots:
        total_ai = sum(c for _, c in bots)
        lines.append(f"**Boty AI ({total_ai} requestów, agent-readiness):**")
        lines.append("")
        lines.append("| bot | requesty |")
        lines.append("|---|---:|")
        for bot, c in bots:
            lines.append(f"| {bot} | {c} |")
        lines.append("")
        if paths:
            top = ", ".join(f"`{p}` ({c})" for p, c in paths[:6])
            lines.append(f"Najczęściej crawlowane ścieżki: {top}")
            lines.append("")

    if status:
        total = sum(c for _, c in status)

        def cls_sum(prefix: int) -> int:
            return sum(c for s, c in status if prefix * 100 <= s < (prefix + 1) * 100)

        c2, c3, c4, c5 = cls_sum(2), cls_sum(3), cls_sum(4), cls_sum(5)
        lines.append(f"**Zdrowie serwisu (brzeg):** {total} requestów — "
                     f"2xx {c2} · 3xx {c3} · 4xx {c4} · 5xx {c5}.")
        detail = {s: c for s, c in status}
        flags = []
        if detail.get(404):
            flags.append(f"404: {detail[404]}")
        for code in (500, 502, 503, 504):
            if detail.get(code):
                flags.append(f"{code}: {detail[code]} (błąd origin)")
        if flags:
            lines.append("- Do sprawdzenia: " + ", ".join(flags) + ".")

    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    import sys
    dbp = os.environ.get("DB_PATH", "marketing_data.db")
    print("=== sync ===", sync_all(dbp))
    print("=== sekcja ===")
    print(build_section(dbp))
