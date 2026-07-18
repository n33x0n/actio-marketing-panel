"""Sekcja 'Trendy na dzisiaj' — kreatywny marketing (newsjacking) dla SENDLY.

Pipeline: pobierz dzisiejsze trendy wyszukiwań (Google Trends RSS, PL) -> LLM ocenia,
które da się wiarygodnie podpiąć pod SMS API SENDLY i mają potencjał na ruch/wpis na
sendly.link, i proponuje kreatywny tekst reklamy -> tabela markdown do raportu.

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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SENDLY report bot)"})
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


ASSESS_PROMPT = """Jesteś strategiem kreatywnego marketingu (newsjacking / real-time marketing) dla SENDLY — SMS API polskiego operatora telekomunikacyjnego (marka spółki Syntell S.A. / ACTIO). Produkt: wysyłka SMS przez REST API, pay-as-you-go, bez pośredników, 100 SMS gratis na start; typowe zastosowania: powiadomienia transakcyjne, kody 2FA/OTP, SMS marketing i masowa wysyłka dla firm oraz e-commerce.

Dostajesz listę dzisiejszych trendów wyszukiwań w Polsce (Google Trends) z kontekstem newsowym. Zadanie: znaleźć te trendy, które da się KREATYWNIE i WIARYGODNIE podpiąć pod markę/usługę SENDLY, tak żeby szybka reakcja reklamowa albo wpis na blogu przyciągnął ruch na sendly.link.

Zasady:
- Zostaw TYLKO trendy z realnym, nienaciąganym powiązaniem z SMS API / powiadomieniami / 2FA / e-commerce / komunikacją z klientem. Lepiej mniej, ale trafnych.
- Odrzucaj naciągane skojarzenia i tematy drażliwe (tragedie, polityka, śmierć) — tam newsjacking szkodzi marce.
- Maksymalnie 10 pozycji. Może być mniej. Może być 0, jeśli nic dziś nie pasuje.

Dla każdego zostawionego trendu podaj:
- "trend": nazwa trendu
- "angle": jak wiarygodnie podpiąć go pod SMS API SENDLY (1 zdanie)
- "blog": czy warto zrobić z tego wpis na blogu, czy to raczej krótka reklama (krótko, np. "tak — poradnik ..." albo "raczej reklama")
- "ad_copy": gotowy, kreatywny tekst reklamy PO POLSKU (1-2 zdania), nawiązujący do trendu i kończący się subtelnym hakiem do SENDLY

Zwróć WYŁĄCZNIE poprawny JSON, bez komentarza, w formacie:
{{"items":[{{"trend":"...","angle":"...","blog":"...","ad_copy":"..."}}]}}

Dzisiejsze trendy (PL):
{trends}
"""


def _assess_llm(trends_json: str) -> list[dict]:
    """Woła OpenRouter (Fable 5 + fallback Opus) i zwraca listę ocenionych trendów."""
    from langfuse.openai import openai
    import os

    brand = get_brand()
    client = openai.OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": brand.openrouter_referer, "X-Title": brand.openrouter_title},
        timeout=120.0,
    )
    prompt = ASSESS_PROMPT.format(trends=trends_json)

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
    """Zwraca sekcję markdown 'Trendy na dzisiaj' albo pusty string (fail-open)."""
    try:
        raw = fetch_trends(geo=geo, limit=20)
        if not raw:
            return ""
        trends_json = json.dumps(raw, ensure_ascii=False, indent=1)
        items = _assess_llm(trends_json)
    except Exception as e:
        print(f"[trends] build error: {type(e).__name__}: {e}")
        return ""

    head = (
        "## 📈 Trendy na dzisiaj (kreatywny marketing)\n\n"
        "Trendy z Google Trends (PL) z potencjałem do szybkiej reakcji reklamowej pod SMS API SENDLY. "
        "Ocena i kreacje wygenerowane automatycznie — zweryfikuj przed publikacją.\n\n"
    )
    if not items:
        return head + "_Dziś brak trendów z sensownym, nienaciąganym powiązaniem z SENDLY._\n"

    rows = ["| Trend | Jak podpiąć pod SENDLY | Na blog? | Sugerowany tekst reklamy |",
            "|---|---|---|---|"]
    for it in items:
        rows.append(
            f"| {_cell(it.get('trend'))} | {_cell(it.get('angle'))} | "
            f"{_cell(it.get('blog'))} | {_cell(it.get('ad_copy'))} |"
        )
    return head + "\n".join(rows) + "\n"


if __name__ == "__main__":
    # Lokalny test parsowania (bez LLM): pokaz surowe trendy.
    for t in fetch_trends():
        n = t["news"][0]["title"] if t["news"] else ""
        print(f"- {t['trend']} ({t['traffic']}) — {n}")
