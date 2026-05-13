"""Panel Positive Report – trendy + period comparison.

Zastępuje obecny panel_view() dla CEO email group (Hubert).
Wywoływany z email_sender.send_report_email().
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from datetime import date, datetime, timedelta

# Load env z .mcp.json
_mcp = pathlib.Path(__file__).parent / ".mcp.json"
if _mcp.exists():
    for _k, _v in json.loads(_mcp.read_text())["mcpServers"]["actio-marketing"]["env"].items():
        os.environ.setdefault(_k, _v)

import markdown as md_lib

import db
import email_sender


DB_PATH = os.environ["DB_PATH"]
TODAY = date.today()

# Sliding window 21d vs 21d
PERIOD_LENGTH = 21


def _compute_periods(today: date) -> tuple[date, date, date, date]:
    """Zwraca (A_start, A_end, B_start, B_end) — sliding 21d vs 21d wstecz od today."""
    b_end = today
    b_start = today - timedelta(days=PERIOD_LENGTH - 1)
    a_end = b_start - timedelta(days=1)
    a_start = a_end - timedelta(days=PERIOD_LENGTH - 1)
    return a_start, a_end, b_start, b_end


PERIOD_A_START, PERIOD_A_END, PERIOD_B_START, PERIOD_B_END = _compute_periods(TODAY)


def _q(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()


def period_metrics(start: date, end: date) -> dict:
    """Aggregate metrics dla zakresu dat."""
    s, e = start.isoformat(), end.isoformat()

    # GA4 total
    ga4 = _q("""
        SELECT SUM(sessions) sessions, SUM(users) users, SUM(conversions) conv
        FROM daily_conversions WHERE date BETWEEN ? AND ?
    """, (s, e))[0]
    ga4_cpc = _q("""
        SELECT SUM(sessions) sessions, SUM(conversions) conv
        FROM daily_conversions
        WHERE date BETWEEN ? AND ? AND source_medium = 'google / cpc'
    """, (s, e))[0]
    ga4_direct = _q("""
        SELECT SUM(conversions) conv
        FROM daily_conversions
        WHERE date BETWEEN ? AND ? AND source_medium = '(direct) / (none)'
    """, (s, e))[0]
    ga4_organic = _q("""
        SELECT SUM(conversions) conv
        FROM daily_conversions
        WHERE date BETWEEN ? AND ? AND source_medium LIKE '%/ organic%'
    """, (s, e))[0]

    # GSC
    gsc = _q("""
        SELECT SUM(impressions) imp, SUM(clicks) clk
        FROM gsc_daily WHERE date BETWEEN ? AND ?
    """, (s, e))[0]

    # Ads
    ads = _q("""
        SELECT SUM(impressions) imp, SUM(clicks) clk, SUM(cost) cost, SUM(conversions) conv
        FROM ads_campaign_daily WHERE date BETWEEN ? AND ?
    """, (s, e))[0]

    return {
        "ga4_sessions": int(ga4["sessions"] or 0),
        "ga4_users": int(ga4["users"] or 0),
        "ga4_conv_total": float(ga4["conv"] or 0),
        "ga4_conv_cpc": float(ga4_cpc["conv"] or 0),
        "ga4_conv_direct": float(ga4_direct["conv"] or 0),
        "ga4_conv_organic": float(ga4_organic["conv"] or 0),
        "ga4_sessions_cpc": int(ga4_cpc["sessions"] or 0),
        "gsc_impressions": int(gsc["imp"] or 0),
        "gsc_clicks": int(gsc["clk"] or 0),
        "ads_impressions": int(ads["imp"] or 0),
        "ads_clicks": int(ads["clk"] or 0),
        "ads_cost": float(ads["cost"] or 0),
        "ads_conv": float(ads["conv"] or 0),
    }


def pct_change(a: float, b: float) -> str:
    if a == 0 and b == 0:
        return "–"
    if a == 0:
        return f"**+∞** (z 0 → {b:.0f}) ⬆️"
    delta = (b - a) / a * 100
    arrow = "⬆️" if delta > 0 else ("⬇️" if delta < 0 else "")
    sign = "+" if delta > 0 else ""
    return f"**{sign}{delta:.0f}%** {arrow}"


def daily_trend(days: int = 7) -> list[dict]:
    """Last N days breakdown – Ads impr/clk + GA4 conv (total + cpc)."""
    s = (TODAY - timedelta(days=days - 1)).isoformat()
    e = TODAY.isoformat()
    rows = _q("""
        WITH dates AS (
            SELECT DISTINCT date FROM gsc_daily WHERE date BETWEEN ? AND ?
            UNION SELECT DISTINCT date FROM ads_campaign_daily WHERE date BETWEEN ? AND ?
            UNION SELECT DISTINCT date FROM daily_conversions WHERE date BETWEEN ? AND ?
        )
        SELECT
            d.date,
            (SELECT SUM(impressions) FROM ads_campaign_daily WHERE date = d.date) ads_imp,
            (SELECT SUM(clicks) FROM ads_campaign_daily WHERE date = d.date) ads_clk,
            (SELECT SUM(conversions) FROM ads_campaign_daily WHERE date = d.date) ads_conv,
            (SELECT SUM(impressions) FROM gsc_daily WHERE date = d.date) gsc_imp,
            (SELECT SUM(clicks) FROM gsc_daily WHERE date = d.date) gsc_clk,
            (SELECT SUM(conversions) FROM daily_conversions WHERE date = d.date) ga4_conv,
            (SELECT SUM(conversions) FROM daily_conversions WHERE date = d.date AND source_medium = 'google / cpc') ga4_conv_cpc
        FROM dates d
        ORDER BY d.date
    """, (s, e, s, e, s, e))
    out = []
    weekday_pl = ["pn", "wt", "śr", "cz", "pt", "sob", "nd"]
    for r in rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d").date()
        out.append({
            "date": d.strftime("%d.%m") + f" ({weekday_pl[d.weekday()]})",
            "ads_imp": int(r["ads_imp"] or 0),
            "ads_clk": int(r["ads_clk"] or 0),
            "gsc_imp": int(r["gsc_imp"] or 0),
            "ga4_conv": float(r["ga4_conv"] or 0),
            "ga4_conv_cpc": float(r["ga4_conv_cpc"] or 0),
        })
    return out


def top_keywords_period(days: int = 30, limit: int = 5) -> list[dict]:
    """Top Ads KW po liczbie conv (sorted by conv desc, then by lowest CPA)."""
    s = (TODAY - timedelta(days=days)).isoformat()
    e = TODAY.isoformat()
    rows = _q("""
        SELECT keyword, match_type, campaign_name,
               SUM(clicks) clicks, SUM(cost) cost, SUM(conversions) conv,
               AVG(quality_score) avg_qs
        FROM ads_keyword_daily
        WHERE date BETWEEN ? AND ? AND conversions > 0
        GROUP BY keyword, match_type, campaign_name
        ORDER BY conv DESC, (cost*1.0 / NULLIF(conv,0)) ASC
        LIMIT ?
    """, (s, e, limit))
    return [dict(r) for r in rows]


def top_pages_gsc(days: int = 30, limit: int = 5) -> list[dict]:
    """Top organic pages po liczbie kliknięć w okresie."""
    s = (TODAY - timedelta(days=days)).isoformat()
    e = TODAY.isoformat()
    rows = _q("""
        SELECT page, SUM(impressions) imp, SUM(clicks) clk, AVG(position) avg_pos
        FROM gsc_daily WHERE date BETWEEN ? AND ?
        GROUP BY page ORDER BY clk DESC, imp DESC
        LIMIT ?
    """, (s, e, limit))
    return [dict(r) for r in rows]


def render_md() -> str:
    A = period_metrics(PERIOD_A_START, PERIOD_A_END)
    B = period_metrics(PERIOD_B_START, PERIOD_B_END)
    trend = daily_trend(8)  # 8 dni żeby było widać 6.05-13.05
    top_kw = top_keywords_period(30, 5)
    top_pages = top_pages_gsc(30, 5)

    def fmt(n, kind="int"):
        if kind == "money":
            return f"{n:,.2f} zł".replace(",", " ").replace(".", ",")
        if kind == "float":
            return f"{n:,.1f}".replace(",", " ").replace(".", ",")
        return f"{int(n):,}".replace(",", " ")

    period_a_str = f"{PERIOD_A_START.strftime('%d.%m')}-{PERIOD_A_END.strftime('%d.%m')}"
    period_b_str = f"{PERIOD_B_START.strftime('%d.%m')}-{PERIOD_B_END.strftime('%d.%m')}"

    md = f"""# 📈 Actio Marketing – Trendy i Wzrosty

**Sliding window porównanie**: poprzednie {PERIOD_LENGTH} dni ({period_a_str}) ▶️ ostatnie {PERIOD_LENGTH} dni ({period_b_str})

---

## ⬆️ Kluczowe wzrosty (porównanie okresów)

| Metryka | {period_a_str} | {period_b_str} | Δ |
|---|---:|---:|---:|
| **Wyświetlenia Google Ads (paid)** | {fmt(A['ads_impressions'])} | {fmt(B['ads_impressions'])} | {pct_change(A['ads_impressions'], B['ads_impressions'])} |
| **Kliki Google Ads** | {fmt(A['ads_clicks'])} | {fmt(B['ads_clicks'])} | {pct_change(A['ads_clicks'], B['ads_clicks'])} |
| **Wydatek Ads** | {fmt(A['ads_cost'], 'money')} | {fmt(B['ads_cost'], 'money')} | {pct_change(A['ads_cost'], B['ads_cost'])} |
| **Wyświetlenia organic (GSC)** | {fmt(A['gsc_impressions'])} | {fmt(B['gsc_impressions'])} | {pct_change(A['gsc_impressions'], B['gsc_impressions'])} |
| **Kliki organic (GSC)** | {fmt(A['gsc_clicks'])} | {fmt(B['gsc_clicks'])} | {pct_change(A['gsc_clicks'], B['gsc_clicks'])} |
| **Sesje (cały ruch)** | {fmt(A['ga4_sessions'])} | {fmt(B['ga4_sessions'])} | {pct_change(A['ga4_sessions'], B['ga4_sessions'])} |
| **Konwersje (wszystkie źródła)** | {fmt(A['ga4_conv_total'], 'float')} | {fmt(B['ga4_conv_total'], 'float')} | {pct_change(A['ga4_conv_total'], B['ga4_conv_total'])} |
| **Konwersje z google/cpc** | {fmt(A['ga4_conv_cpc'], 'float')} | {fmt(B['ga4_conv_cpc'], 'float')} | {pct_change(A['ga4_conv_cpc'], B['ga4_conv_cpc'])} |
| **Konwersje direct** | {fmt(A['ga4_conv_direct'], 'float')} | {fmt(B['ga4_conv_direct'], 'float')} | {pct_change(A['ga4_conv_direct'], B['ga4_conv_direct'])} |

---

## 📅 Daily trend (ostatnie 8 dni)

| Data | Wyśw Ads | Kliki Ads | Wyśw GSC | Konw (all) | Konw cpc |
|---|---:|---:|---:|---:|---:|
"""
    for t in trend:
        md += f"| {t['date']} | {fmt(t['ads_imp'])} | {fmt(t['ads_clk'])} | {fmt(t['gsc_imp'])} | {fmt(t['ga4_conv'], 'float')} | {fmt(t['ga4_conv_cpc'], 'float')} |\n"

    md += f"""
---

## 🏆 Top 5 keywords (Google Ads, 30d, po konwersjach)

| # | Keyword | Match | Kampania | Kliki | Koszt | Konw | CPA |
|---|---|---|---|---:|---:|---:|---:|
"""
    if top_kw:
        for i, k in enumerate(top_kw, 1):
            cpa = k['cost'] / k['conv'] if k['conv'] > 0 else 0
            md += f"| {i} | `{k['keyword']}` | {k['match_type'][0]} | {k['campaign_name'].replace('SEARCH_', '')} | {fmt(k['clicks'])} | {fmt(k['cost'], 'money')} | {fmt(k['conv'], 'float')} | {fmt(cpa, 'money')} |\n"
    else:
        md += "| – | (brak konwersji w 30d) | | | | | | |\n"

    md += f"""
---

## 🔎 Top 5 stron organic (GSC, 30d)

| # | Strona | Wyświetlenia | Kliki | Avg pozycja |
|---|---|---:|---:|---:|
"""
    for i, p in enumerate(top_pages, 1):
        short = p["page"].replace("https://actio.pl", "") or "/"
        md += f"| {i} | `{short}` | {fmt(p['imp'])} | {fmt(p['clk'])} | {p['avg_pos']:.1f} |\n"

    md += f"""
---

## 🚀 Co zostało wdrożone (10-13.05)

- **24/7 schedule** dla wszystkich 9 kampanii (poprzednio Pn-Pt 8-16) – łapiemy wieczorne queries
- **BRAND budget**: 30 zł/d → 100 zł/d (unified), bid 2,50→3,50, dziś **Smart Bidding** (Maximize Conversions)
- **Mobile bid modifier**: -90% → -20% (60-70% PL search to mobile, otwarliśmy ten kanał)
- **Nowa kampania SEARCH_3G_LIKWIDACJA_PL** – time-sensitive (operatorzy gaszą 3G)
- **GTM enrichment** – od teraz wiemy które formularze (2485 vs 123446) i numery telefonów (BOK vs Pomoc) generują leady
- **Bid bumpy** na SIPTRUNK/VOIP/KOMORKI/SMSAPI (10.05) – łapanie premium aukcji
- **3 nowe high-intent keywords**: `voip dla biznesu`, `wdrożenie voip`, `voip poznań`, `system voip dla firmy`
- **Autopublisher WP postów** (uruchomiony 13.05) – wt+pt 9:00 generuje content blog z LLM, akceptacja mailem

---

## ℹ️ Notatka metodologiczna

- Konwersje GA4: event `generate_lead` (formularz CF7 lub klik tel:) – różni się od Google Ads attribution (Ads liczy klik-conversion 30d window, GA4 last-click sesji)
- "Konwersje direct" to często **pokłosie reklam** – user widzi ad, googluje brand za 1-3 dni, wchodzi direct, konwertuje

"""
    return md


def _wrap_html(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 760px; margin: 0 auto; padding: 16px; color: #222; }}
h1 {{ font-size: 22px; }} h2 {{ font-size: 18px; margin-top: 28px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #e1e4e8; padding: 6px 10px; text-align: left; font-size: 14px; }}
th {{ background: #f6f8fa; }}
code {{ background: #f0f0f0; padding: 1px 5px; border-radius: 3px; font-size: 13px; }}
strong {{ color: #1f883d; }}
hr {{ border: 0; border-top: 1px solid #ddd; margin: 24px 0; }}
</style></head><body>
{body_html}
</body></html>"""


def generate(today_iso: str | None = None) -> dict:
    """Public entry – zwraca {subject, plain, html} dla danego dnia."""
    global TODAY, PERIOD_A_START, PERIOD_A_END, PERIOD_B_START, PERIOD_B_END
    if today_iso:
        TODAY = datetime.strptime(today_iso, "%Y-%m-%d").date()
    PERIOD_A_START, PERIOD_A_END, PERIOD_B_START, PERIOD_B_END = _compute_periods(TODAY)
    md = render_md()
    inner_html = md_lib.markdown(md, extensions=["extra", "tables", "fenced_code"])
    html = _wrap_html(inner_html)
    subject = f"[Actio Marketing Report] 📈 – {TODAY.strftime('%Y-%m-%d')}"
    return {"subject": subject, "plain": md, "html": html}


if __name__ == "__main__":
    print("=== Generating Panel Positive Report ===")
    pkg = generate()
    pathlib.Path("/tmp/panel_positive_preview.html").write_text(pkg["html"], encoding="utf-8")
    print(f"Subject: {pkg['subject']}")
    print("Sending to tlebioda@gmail.com (test override)")
    email_sender._send_via_gmail(["tlebioda@gmail.com"], pkg["subject"], pkg["html"], pkg["plain"])
    print("Done.")
