"""Sekcja 'Trendy na dzisiaj' — kreatywny marketing (newsjacking), per marka.

Pipeline: pobierz dzisiejsze trendy wyszukiwań (Google Trends RSS, PL) -> LLM ocenia,
które da się wiarygodnie podpiąć pod ofertę marki, i proponuje gotową treść
-> tabela markdown do raportu.

Prompt, kolumny tabeli i teksty sekcji pochodzą z profilu marki (brand_config:
trends_prompt / trends_fields / trends_intro / trends_empty), więc ACTIO i SENDLY
mają własne, dopasowane wersje na wspólnym kodzie.

Wszystko fail-open: dowolny błąd (sieć, LLM, parsowanie) -> pusty string, raport idzie dalej.
Sekcja trafia do OBU raportów (CMO Tom + CEO Hubert).
"""
from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from brand_config import get_brand

HT_NS = "https://trends.google.com/trending/rss"


def fetch_trends(geo: str = "PL", limit: int = 20) -> list[dict]:
    """Pobiera trendujące wyszukiwania z Google Trends RSS. Zwraca [{trend, traffic, news[]}]."""
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (marketing report bot)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode("utf-8", errors="replace")
    root = ET.fromstring(raw)
    out: list[dict] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = (item.findtext(f"{{{HT_NS}}}approx_traffic") or "").strip()
        news = []
        for ni in item.findall(f"{{{HT_NS}}}news_item"):
            nt = (ni.findtext(f"{{{HT_NS}}}news_item_title") or "").strip()
            ns_ = (ni.findtext(f"{{{HT_NS}}}news_item_snippet") or "").strip()
            if nt or ns_:
                news.append({"title": nt, "snippet": ns_})
        out.append({"trend": title, "traffic": traffic, "news": news[:2]})
        if len(out) >= limit:
            break
    return out


def _assess_llm(trends_json: str) -> list[dict]:
    """Woła OpenRouter (Fable 5 + fallback Opus) z promptem PROFILU MARKI. Zwraca oceny."""
    from langfuse.openai import openai
    import os

    brand = get_brand()
    client = openai.OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": brand.openrouter_referer, "X-Title": brand.openrouter_title},
        timeout=120.0,
    )
    prompt = brand.trends_prompt.format(trends=trends_json)

    def _call(model: str) -> str | None:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=6000,
            extra_body={"provider": {"data_collection": "deny"}},
            name="daily_report_trends",
            metadata={"source": "trends.py", "use_case": "creative_marketing_trends"},
        )
        return resp.choices[0].message.content

    primary = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-fable-5")
    fallback = os.environ.get("OPENROUTER_FALLBACK_MODEL", "anthropic/claude-opus-4.8")
    raw = None
    try:
        raw = _call(primary)
    except Exception as e:
        print(f"[trends] {primary} padl ({type(e).__name__}: {e}) - fallback")
    if not (raw and raw.strip()):
        raw = _call(fallback)

    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return []
    data = json.loads(m.group(0))
    items = data.get("items", []) if isinstance(data, dict) else []
    return items[:10]


def _cell(text: str) -> str:
    """Sanityzacja komórki tabeli markdown: bez | i bez łamania wiersza."""
    return re.sub(r"\s+", " ", str(text or "").replace("|", "/")).strip()


def build_trends_section(geo: str = "PL") -> str:
    """Zwraca sekcję markdown 'Trendy na dzisiaj' dla AKTYWNEJ MARKI albo "" (fail-open)."""
    brand = get_brand()
    if not brand.trends_prompt:
        return ""
    try:
        raw = fetch_trends(geo=geo, limit=20)
        if not raw:
            return ""
        trends_json = json.dumps(raw, ensure_ascii=False, indent=1)
        items = _assess_llm(trends_json)
    except Exception as e:
        print(f"[trends] build error: {type(e).__name__}: {e}")
        return ""

    head = f"## 📈 Trendy na dzisiaj (kreatywny marketing)\n\n{brand.trends_intro}\n\n"
    if not items:
        result = head + brand.trends_empty + "\n"
    else:
        keys = [k for k, _ in brand.trends_fields]
        headers = [h for _, h in brand.trends_fields]
        rows = ["| " + " | ".join(headers) + " |",
                "|" + "---|" * len(headers)]
        for it in items:
            rows.append("| " + " | ".join(_cell(it.get(k)) for k in keys) + " |")
        result = head + "\n".join(rows) + "\n"
    # Reguła Toma: w sekcji trendów wszędzie półpauzy (–), nigdy pauzy (—); LLM lubi wstawiać pauzy.
    return result.replace("—", "–")


if __name__ == "__main__":
    # Lokalny test parsowania (bez LLM): pokaz surowe trendy.
    for t in fetch_trends():
        n = t["news"][0]["title"] if t["news"] else ""
        print(f"- {t['trend']} ({t['traffic']}) — {n}")
