"""AI bot crawl monitor – czyta endpoint actio.pl/wp-json/actio/v1/ai-bots
(mu-plugin actio-ai-bot-logger.php) i buduje sekcję do raportu CMO/GEO.

Pozwala wydedukować: które boty AI realnie czytają actio.pl, w jakim celu
(retrieval/cytowanie vs trening) i które strony. Korelujemy z AI Share of Voice.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.request

BASE_DIR = pathlib.Path(__file__).resolve().parent


def _env(key: str, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    try:
        cfg = json.loads((BASE_DIR / ".mcp.json").read_text())
        return cfg["mcpServers"]["actio-marketing"]["env"].get(key, default)
    except Exception:
        return default


def fetch(days: int = 7) -> dict | None:
    token = _env("ACTIO_AIBOT_TOKEN")
    if not token:
        return None
    url = f"https://actio.pl/wp-json/actio/v1/ai-bots?token={token}&days={days}"
    req = urllib.request.Request(url, headers={"User-Agent": "actio-cmo/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _purpose_line(d: dict | None) -> str:
    if not d:
        return "-"
    bp = {r["purpose"]: int(r["hits"]) for r in d.get("by_purpose", [])}
    return f"retrieval/cytowanie {bp.get('search', 0)} · trening {bp.get('train', 0)} · inne {bp.get('other', 0)}"


def build_section(days: int = 30) -> list[str]:
    """Sekcja: puls 7 dni + szczegoly 30 dni (tabela botow + top strony)."""
    if not _env("ACTIO_AIBOT_TOKEN"):
        return ["### Boty AI na actio.pl", "(brak ACTIO_AIBOT_TOKEN – pomijam)"]
    try:
        d7 = fetch(7)
        d30 = fetch(30)
    except Exception as e:
        return ["### Boty AI na actio.pl", f"(błąd odczytu: {type(e).__name__}: {e})"]

    t7 = d7.get("total", 0) if d7 else 0
    t30 = d30.get("total", 0) if d30 else 0
    out = ["### Boty AI czytające actio.pl", ""]
    out.append(f"**Ostatnie 7 dni: {t7} wizyt** — {_purpose_line(d7)}")
    out.append("")
    out.append(f"**Z ostatnich 30 dni: {t30} wizyt** — {_purpose_line(d30)}")

    if t30 == 0:
        out.append("")
        out.append("_Brak wizyt botów AI. Jeśli się utrzyma → AI nas nie pobiera = nie ma z czego cytować._")
        return out

    by_bot = (d30 or {}).get("by_bot", [])
    if by_bot:
        out.append("")
        out.append("**Wg bota (30 dni):**")
        out.append("")
        out.append("| bot | cel | wizyty | ostatnio |")
        out.append("|---|---|---:|---|")
        for r in by_bot[:12]:
            out.append(f"| {r['bot']} | {r['purpose']} | {r['hits']} | {str(r['last_seen'])[:10]} |")
    tp = (d30 or {}).get("top_paths", [])
    if tp:
        out.append("")
        out.append("**Najczęściej czytane (30 dni):**")
        out.append("")
        out.append("| strona | wizyty |")
        out.append("|---|---:|")
        for p in tp[:8]:
            out.append(f"| `{p['path'][:60]}` | {p['hits']} |")
    return out


if __name__ == "__main__":
    print("\n".join(build_section(30)))
