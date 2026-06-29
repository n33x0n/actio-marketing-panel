"""AI bot crawl monitor – czyta lokalny SQLite (tabela ai_bot_hits, zasilana przez
CF Pages middleware -> POST /autopost/aibot na Mikrusie; replatform z mu-plugin
actio-ai-bot-logger.php po migracji actio.pl na Cloudflare Pages).

Pozwala wydedukować: które boty AI realnie czytają actio.pl, w jakim celu
(retrieval/cytowanie vs trening) i które strony. Korelujemy z AI Share of Voice.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3

BASE_DIR = pathlib.Path(__file__).resolve().parent


def _env(key: str, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    try:
        cfg = json.loads((BASE_DIR / ".mcp.json").read_text())
        return cfg["mcpServers"]["actio-marketing"]["env"].get(key, default)
    except Exception:
        return default


def _db_path() -> str | None:
    val = os.environ.get("DB_PATH")
    if val:
        return val
    try:
        cfg = json.loads((BASE_DIR / ".mcp.json").read_text())
        return cfg["mcpServers"]["actio-marketing"]["env"].get("DB_PATH")
    except Exception:
        return None


def fetch(days: int = 7) -> dict | None:
    """Agregaty wizyt botów AI z lokalnej tabeli ai_bot_hits (ten sam kształt
    co dawniej zwracał WP REST: total / by_bot / by_purpose / top_paths)."""
    path = _db_path()
    if not path:
        return None
    empty = {"days": days, "total": 0, "by_bot": [], "by_purpose": [], "top_paths": []}
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
    except Exception:
        return None
    since = f"-{int(days)} days"
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_bot_hits'")
        if not cur.fetchone():
            return empty
        total = cur.execute(
            "SELECT count(*) FROM ai_bot_hits WHERE hit_time >= datetime('now', ?)", (since,)
        ).fetchone()[0]
        by_bot = [dict(r) for r in cur.execute(
            "SELECT bot, purpose, count(*) hits, min(hit_time) first_seen, max(hit_time) last_seen "
            "FROM ai_bot_hits WHERE hit_time >= datetime('now', ?) GROUP BY bot, purpose ORDER BY hits DESC", (since,))]
        by_purpose = [dict(r) for r in cur.execute(
            "SELECT purpose, count(*) hits FROM ai_bot_hits WHERE hit_time >= datetime('now', ?) GROUP BY purpose", (since,))]
        top_paths = [dict(r) for r in cur.execute(
            "SELECT path, count(*) hits FROM ai_bot_hits WHERE hit_time >= datetime('now', ?) "
            "GROUP BY path ORDER BY hits DESC LIMIT 25", (since,))]
        return {"days": days, "total": total, "by_bot": by_bot, "by_purpose": by_purpose, "top_paths": top_paths}
    except Exception:
        return empty
    finally:
        conn.close()


def _purpose_line(d: dict | None) -> str:
    if not d:
        return "-"
    bp = {r["purpose"]: int(r["hits"]) for r in d.get("by_purpose", [])}
    return f"retrieval/cytowanie {bp.get('search', 0)} · trening {bp.get('train', 0)} · inne {bp.get('other', 0)}"


def build_section(days: int = 30) -> list[str]:
    """Sekcja: puls 7 dni + szczegoly 30 dni (tabela botow + top strony)."""
    try:
        d7 = fetch(7)
        d30 = fetch(30)
    except Exception as e:
        return ["### Boty AI na actio.pl", f"(błąd odczytu: {type(e).__name__}: {e})"]

    t7 = d7.get("total", 0) if d7 else 0
    t30 = d30.get("total", 0) if d30 else 0
    out = ["### Boty AI czytające actio.pl"]
    out.append(f"**Ostatnie 7 dni: {t7} wizyt** — {_purpose_line(d7)}")
    out.append(f"**Z ostatnich 30 dni: {t30} wizyt** — {_purpose_line(d30)}")

    if t30 == 0:
        out.append("_Brak wizyt botów AI. Jeśli się utrzyma → AI nas nie pobiera = nie ma z czego cytować._")
        return out

    by_bot = (d30 or {}).get("by_bot", [])
    if by_bot:
        out.append("")
        out.append("Wg bota (30 dni):")
        out.append("| bot | cel | wizyty | ostatnio |")
        out.append("|---|---|---:|---|")
        for r in by_bot[:12]:
            out.append(f"| {r['bot']} | {r['purpose']} | {r['hits']} | {str(r['last_seen'])[:10]} |")
    tp = (d30 or {}).get("top_paths", [])
    if tp:
        out.append("")
        out.append("Najczęściej czytane (30 dni): " + ", ".join(f"`{p['path'][:48]}` ({p['hits']})" for p in tp[:6]))
    return out


if __name__ == "__main__":
    print("\n".join(build_section(30)))
