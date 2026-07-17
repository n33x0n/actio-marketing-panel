"""Google Search Console Data API wrapper — date × query × page per site."""
from __future__ import annotations

from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from brand_config import get_brand


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_LAG_DAYS = 3  # GSC dane nie są stabilne dla ostatnich 2-3 dni


def _client():
    creds, _ = _load_credentials()
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def _load_credentials():
    import os
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if path:
        creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        return creds, path
    from google.auth import default
    return default(scopes=SCOPES)


def list_sites() -> list[dict]:
    """Lista property do których SA ma dostęp."""
    svc = _client()
    resp = svc.sites().list().execute()
    return [
        {"site_url": s["siteUrl"], "permission": s["permissionLevel"]}
        for s in resp.get("siteEntry", [])
    ]


def _brand_sites() -> list[dict]:
    """list_sites() zawezone do property marki (brand.gsc_site_filter).

    Actio ma gsc_site_filter=None -> wszystkie property (bez zmiany zachowania).
    Sendly ma allowliste (sc-domain:sendly.link) -> izolacja od actio.pl w tej samej bazie.
    """
    sites = list_sites()
    allow = get_brand().gsc_site_filter
    if allow:
        sites = [s for s in sites if s["site_url"] in allow]
    return sites


def fetch_last_7_days(site_url: str) -> list[dict]:
    """date × query × page dla jednej property, ostatnie 7 dni (minus 3-dniowy lag GSC)."""
    svc = _client()
    end_date = date.today() - timedelta(days=GSC_LAG_DAYS)
    start_date = end_date - timedelta(days=7)

    all_rows: list[dict] = []
    start_row = 0
    row_limit = 25000

    while True:
        resp = svc.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": str(start_date),
                "endDate": str(end_date),
                "dimensions": ["date", "query", "page"],
                "rowLimit": row_limit,
                "startRow": start_row,
            },
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            break

        for r in rows:
            d, q, p = r["keys"]
            all_rows.append({
                "date": d,
                "site_url": site_url,
                "query": q,
                "page": p,
                "impressions": int(r["impressions"]),
                "clicks": int(r["clicks"]),
                "ctr": float(r["ctr"]),
                "position": float(r["position"]),
            })

        if len(rows) < row_limit:
            break
        start_row += row_limit

    return all_rows


def fetch_seo_opportunities(
    site_url: str, days: int = 28, min_impressions: int = 25, top: int = 12
) -> list[dict]:
    """Strony z widocznością (impresje) ale ~0 klików — kandydaci do poprawy.

    Operacjonalizuje content-refresh: znajdź strony które już rankują, ale nie
    dowożą klików. Dodatkowo wykrywa jezykowy mismatch (polska fraza serwowana
    pod /en//de//ua/) — to najczęstsza przyczyna 0% CTR na świeżej domenie.
    """
    import re

    svc = _client()
    end_date = date.today() - timedelta(days=GSC_LAG_DAYS)
    start_date = end_date - timedelta(days=days)
    resp = svc.searchanalytics().query(
        siteUrl=site_url,
        body={
            "startDate": str(start_date),
            "endDate": str(end_date),
            "dimensions": ["page", "query"],
            "rowLimit": 5000,
        },
    ).execute()
    rows = resp.get("rows", [])

    PL_DIA = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
    PL_WORDS = {
        "cennik", "kosztuje", "wysyłka", "wysylka", "ile", "dla", "polsce", "polska",
        "najlepsze", "tanie", "bramka", "powiadomienia", "urząd", "urzędu", "urzędów",
        "gmina", "gminy", "jak", "cena", "ceny", "porównanie", "masowa",
    }

    def looks_polish(q: str) -> bool:
        if any(ch in PL_DIA for ch in q):
            return True
        toks = set(re.findall(r"[a-ząćęłńóśźż]+", q.lower()))
        return bool(toks & PL_WORDS)

    def lang_of(page: str) -> str:
        m = re.search(r"^https?://[^/]+/([a-z]{2})/", page)
        return m.group(1) if m else "?"

    pages: dict[str, dict] = {}
    for r in rows:
        page, query = r["keys"]
        imp, clk, pos = int(r["impressions"]), int(r["clicks"]), float(r["position"])
        p = pages.setdefault(page, {"imp": 0, "clk": 0, "pos_w": 0.0, "tq": "", "tq_imp": 0})
        p["imp"] += imp
        p["clk"] += clk
        p["pos_w"] += pos * imp
        if imp > p["tq_imp"]:
            p["tq_imp"], p["tq"] = imp, query

    out: list[dict] = []
    for page, p in pages.items():
        if p["imp"] < min_impressions:
            continue
        ctr = p["clk"] / max(p["imp"], 1)
        if ctr > 0.005:  # ma realne kliki -> nie "0 klików"
            continue
        lang = lang_of(page)
        mismatch = lang in ("en", "de", "ua") and looks_polish(p["tq"])
        out.append({
            "strona": re.sub(r"^https?://[^/]+", "", page),
            "jezyk": lang,
            "impresje": p["imp"],
            "klik": p["clk"],
            "poz": round(p["pos_w"] / max(p["imp"], 1), 1),
            "top_zapytanie": p["tq"],
            "flaga": f"ZLY JEZYK (PL fraza na /{lang}/)" if mismatch else ("0 klikow" if p["clk"] == 0 else "niski CTR"),
        })
    out.sort(key=lambda x: (0 if "ZLY JEZYK" in x["flaga"] else 1, -x["impresje"]))
    return out[:top]


def fetch_totals_last_7_days(site_url: str) -> list[dict]:
    """Totale per data (BEZ wymiaru query) — pelne kliki/impresje.

    UWAGA: pobranie z wymiarem `query` (fetch_last_7_days) WYCINA zapytania
    anonimizowane — dla actio.pl to ~95% klikow (zweryfikowane 08.07: 44 vs 2
    kliki na tym samym oknie). KPI klikow liczyc z TEJ tabeli; wiersze
    per-query sluza tylko do analizy fraz.
    """
    svc = _client()
    end_date = date.today() - timedelta(days=GSC_LAG_DAYS)
    start_date = end_date - timedelta(days=7)
    resp = svc.searchanalytics().query(
        siteUrl=site_url,
        body={
            "startDate": str(start_date),
            "endDate": str(end_date),
            "dimensions": ["date"],
            "rowLimit": 1000,
        },
    ).execute()
    return [
        {
            "date": r["keys"][0],
            "site_url": site_url,
            "impressions": int(r["impressions"]),
            "clicks": int(r["clicks"]),
            "ctr": float(r["ctr"]),
            "position": float(r["position"]),
        }
        for r in resp.get("rows", [])
    ]


def fetch_all_sites_totals() -> list[dict]:
    """Totale per data dla wszystkich property (odpowiednik fetch_all_sites_last_7_days)."""
    rows: list[dict] = []
    for site in _brand_sites():
        rows.extend(fetch_totals_last_7_days(site["site_url"]))
    return rows


def fetch_all_sites_last_7_days() -> tuple[list[dict], list[str]]:
    """Ostatnie 7 dni dla wszystkich property do których SA ma dostęp.

    Returns:
        (rows, sites) — wiersze gotowe dla db.upsert_gsc_rows + lista
        przepytanych site_url.
    """
    sites = _brand_sites()
    all_rows: list[dict] = []
    processed: list[str] = []

    for site in sites:
        rows = fetch_last_7_days(site["site_url"])
        all_rows.extend(rows)
        processed.append(site["site_url"])

    return all_rows, processed
