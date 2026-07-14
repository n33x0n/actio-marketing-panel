"""GEO / AI Share of Voice monitor.

Odpytuje silniki AI (przez OpenRouter) stalym panelem zapytan kupujacych B2B VoIP
i mierzy, czy/jak Actio jest wymieniane vs konkurencja. Loguje do SQLite (tabela
geo_visibility) i liczy KPI 'AI Share of Voice'. Bialy kapelusz: tylko MONITORING
widocznosci, zero manipulacji.

Uruchamianie (na Mikrusie):  python geo_monitor.py
Cykl docelowy: co 2 tygodnie (systemd timer).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
from datetime import date, datetime, timezone

import httpx

from brand_config import get_brand

BASE_DIR = pathlib.Path(__file__).resolve().parent
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Panel benchmark – realne intencje kupujacych B2B VoIP (PL). Staly, nie zmieniac
# bez powodu (porownywalnosc w czasie).
QUERIES = [
    "najlepszy operator VoIP dla firm w Polsce",
    "VoIP dla firm ktory operator wybrac",
    "ranking operatorow VoIP dla firm 2026",
    "operator VoIP B2B Polska",
    "ranking wirtualnych central telefonicznych dla firm 2026",
    "porownanie SIP trunk dla firm w Polsce",
    "3CX wdrozenie Polska partner",
    "ranking dostawcow SMS API w Polsce",
    "wirtualny numer komorkowy VoIP dla firm",
]

# Marki do wykrywania (Actio + konkurenci z analizy konkurencji 17.06).
BRANDS = {
    "Actio": r"\bactio\b",
    "EasyCall": r"\beasy ?call\b",
    "FCN": r"\bfcn\b",
    "Zadarma": r"\bzadarma\b",
    "Welyo": r"\bwelyo\b",
    "Halonet": r"\bhalo ?net\b",
    "PLFON": r"\bplfon\b|peoplefone",
    "Platan": r"\bplatan\b",
    "Telestrada": r"\btelestrada\b",
    "Spikon": r"\bspikon\b",
    "Ringostat": r"\bringostat\b",
    "SuperVoIP": r"\bsupervoip\b",
    "TeleCube": r"\btelecube\b",
    "Systell": r"\bsystell\b",
    "Fonet": r"\bfonet\b",
    "Aiton Caldwell": r"aiton\s*caldwell",
    "VoIPStudio": r"\bvoip ?studio\b",
    "Orange": r"\borange\b",
    "smsapi": r"\bsmsapi\b",
}

# Silniki przez OpenRouter: live-web (Perplexity) + parametryczny (z .mcp.json).
SYSTEM_PROMPT = (
    "Jestes asystentem doradzajacym polskim firmom wybor dostawcy uslug telekomunikacyjnych/VoIP. "
    "Odpowiadaj po polsku, rzeczowo, i wymieniaj KONKRETNYCH dostawcow/operatorow z nazwy. "
    "Maksymalnie kilka zdan."
)


def _env(key: str, default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    try:
        cfg = json.loads((BASE_DIR / ".mcp.json").read_text())
        return cfg["mcpServers"]["actio-marketing"]["env"].get(key, default)
    except Exception:
        return default


def _engines() -> list[dict]:
    # Chatboty w trybie :online (OpenRouter dokleja web-search) – odwzorowuje realne
    # odpowiedzi konsumenckich chatbotów (które korzystają z sieci). + parametryczny baseline.
    out = [
        {"label": "perplexity-sonar", "model": "perplexity/sonar", "kind": "live-web"},
        {"label": "chatgpt", "model": "openai/gpt-5.4:online", "kind": "live-web"},
        {"label": "claude", "model": "anthropic/claude-sonnet-4.6:online", "kind": "live-web"},
        {"label": "gemini", "model": "google/gemini-2.5-flash:online", "kind": "live-web"},
        {"label": "grok", "model": "x-ai/grok-4.3:online", "kind": "live-web"},
    ]
    param = _env("OPENROUTER_MODEL") or "openai/gpt-5.4"
    out.append({"label": "parametric", "model": param, "kind": "parametric"})
    return out


def ask(model: str, query: str, api_key: str) -> str:
    r = httpx.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": get_brand().openrouter_referer,
            "X-Title": f"{get_brand().name} GEO Monitor",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": get_brand().geo_system_prompt},
                {"role": "user", "content": query},
            ],
            "temperature": 0,
            "max_tokens": 600,
        },
        timeout=90.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def analyze(text: str) -> dict:
    """Wykryj marki + pozycje marki docelowej wsrod wymienionych (kolumny actio_* = target)."""
    b = get_brand()
    target = b.geo_target
    low = text.lower()
    hits = []  # (idx, brand)
    for brand, pat in b.geo_brands.items():
        m = re.search(pat, low)
        if m:
            hits.append((m.start(), brand))
    hits.sort()
    ordered = [x for _, x in hits]
    found = target in ordered
    rank = ordered.index(target) + 1 if found else None
    competitors = [x for x in ordered if x != target]
    # snippet ze zdaniem o marce docelowej
    snippet = ""
    if found:
        mm = re.search(rf"[^.\n]*(?:{b.geo_brands[target]})[^.\n]*", text, re.I)
        snippet = (mm.group(0).strip() if mm else text[:200])[:300]
    return {
        "actio_mentioned": found,
        "actio_rank": rank,
        "brands_ordered": ordered,
        "competitors": competitors,
        "snippet": snippet,
    }


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS geo_visibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            run_ts TEXT NOT NULL,
            query TEXT NOT NULL,
            engine TEXT NOT NULL,
            model TEXT NOT NULL,
            actio_mentioned INTEGER NOT NULL,
            actio_rank INTEGER,
            competitors TEXT NOT NULL DEFAULT '[]',
            brands_ordered TEXT NOT NULL DEFAULT '[]',
            snippet TEXT,
            error TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geo_run ON geo_visibility(run_date)")
    conn.commit()
    return conn


def run(run_date: str | None = None) -> dict:
    api_key = _env("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Brak OPENROUTER_API_KEY w .mcp.json/env")
    db_path = _env("DB_PATH") or str(BASE_DIR / "marketing_data.db")
    run_date = run_date or date.today().isoformat()
    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = _db(db_path)
    engines = _engines()
    queries = get_brand().geo_queries

    rows = []
    comp_counter: dict[str, int] = {}
    per_engine: dict[str, list[bool]] = {e["label"]: [] for e in engines}

    for q in queries:
        for e in engines:
            rec = {"query": q, "engine": e["label"], "model": e["model"], "error": None}
            try:
                txt = ask(e["model"], q, api_key)
                a = analyze(txt)
                rec.update(a)
                for c in a["competitors"]:
                    comp_counter[c] = comp_counter.get(c, 0) + 1
                per_engine[e["label"]].append(a["actio_mentioned"])
            except Exception as ex:
                rec.update({"actio_mentioned": False, "actio_rank": None,
                            "competitors": [], "brands_ordered": [], "snippet": "",
                            "error": f"{type(ex).__name__}: {ex}"})
                per_engine[e["label"]].append(False)
            conn.execute(
                """INSERT INTO geo_visibility
                   (run_date,run_ts,query,engine,model,actio_mentioned,actio_rank,competitors,brands_ordered,snippet,error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (run_date, run_ts, q, rec["engine"], rec["model"], int(rec["actio_mentioned"]),
                 rec["actio_rank"], json.dumps(rec["competitors"], ensure_ascii=False),
                 json.dumps(rec["brands_ordered"], ensure_ascii=False), rec["snippet"], rec["error"]),
            )
            rows.append(rec)
    conn.commit()
    conn.close()

    total = len(rows)
    actio_hits = sum(1 for r in rows if r["actio_mentioned"])
    unique_q = len({r["query"] for r in rows if r["actio_mentioned"]})
    return {
        "run_date": run_date,
        "rows": rows,
        "kpi_share_of_voice": round(actio_hits / total, 3) if total else 0,
        "actio_in_queries": f"{unique_q}/{len(queries)}",
        "per_engine": {k: f"{sum(v)}/{len(v)}" for k, v in per_engine.items()},
        "top_competitors": sorted(comp_counter.items(), key=lambda x: -x[1])[:8],
        "db_path": db_path,
    }


if __name__ == "__main__":
    res = run()
    print(f"=== GEO AI Share of Voice – {res['run_date']} ===")
    print(f"KPI Share of Voice (Actio / wszystkie odpowiedzi): {res['kpi_share_of_voice']*100:.0f}%")
    print(f"Actio wspomniane w zapytaniach (ktorykolwiek silnik): {res['actio_in_queries']}")
    print(f"Per silnik: {res['per_engine']}")
    print(f"Top konkurenci (liczba wzmianek): {res['top_competitors']}")
    print("\n--- gdzie Actio NIEOBECNE (luki) ---")
    absent = {}
    for r in res["rows"]:
        absent.setdefault(r["query"], []).append(r["actio_mentioned"])
    for q, hits in absent.items():
        if not any(hits):
            print(f"  [BRAK] {q}")
    print(f"\nDB: {res['db_path']} (tabela geo_visibility)")
