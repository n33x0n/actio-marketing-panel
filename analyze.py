"""CMO-layer — fresh sync wszystkich źródeł + analiza Opus 4.7 (przez OpenRouter)
+ zapis raportu do Obsidiana + push na telefon."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import urllib.parse

import httpx
import pandas as pd

import ads
import alerts
import db
import email_sender
import ga4
import gsc


def _load_env_from_mcp_json() -> None:
    """Fallback dla CLI — wczytaj env z .mcp.json jeśli zmienne nie są ustawione."""
    mcp_path = pathlib.Path(__file__).parent / ".mcp.json"
    if not mcp_path.exists():
        return
    try:
        cfg = json.loads(mcp_path.read_text())
        env = cfg["mcpServers"]["actio-marketing"]["env"]
        for k, v in env.items():
            os.environ.setdefault(k, v)
    except Exception:
        pass


_load_env_from_mcp_json()


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Brak zmiennej środowiskowej: {name}")
    return val


REPORT_PROMPT = """Jesteś senior performance marketing CMO dla firmy Actio (B2B VoIP / telefonia internetowa).

KRYTYCZNE: poniżej masz LIVE state konta (kampanie i negatywy bezpośrednio z API). To jest ŹRÓDŁO PRAWDY.
Jeśli search term/keyword wygląda na śmieciowy ale jest już w aktywnych negatywach — NIE sugeruj go ponownie dodawać (to historia w 7-dniowym oknie sprzed dodania negatywu).
Jeśli kampania jest ENABLED w live state — NIE sugeruj jej pauzowania ze względu na "powinna być wstrzymana".

### LIVE state konta (źródło prawdy, {date})
{live_account_state}

Realny lead-event w GA4 to `generate_lead` (klik tel: + submit form na /kontakt/ + form na landingach inline).
Lead source (`generate_lead`) jest poprawnie skonfigurowany.

Mając poniższe dane, napisz **krótki raport po polsku** w formacie markdown z trzema sekcjami:

## Daily digest
1-2 zdania: co się stało ostatnio. Podaj konkretne liczby (kliknięcia, koszt, konwersje, CPA jeśli istotny).

## Anomalie
Lista 0-5 punktów. Każdy punkt: co odbiega od normy + konkretne liczby. Tylko realne anomalie — jeśli nic się nie wyróżnia, napisz "brak istotnych anomalii".

**WAŻNE — klasyfikacja każdej anomalii**:
- **Zacznij każdy punkt od emoji** — 🟢 jeśli to anomalia pozytywna (wzrost, sukces, lepszy wynik niż norma, rekord) lub 🔴 jeśli negatywna (spadek, problem, gorszy wynik, zmarnowany budżet, wysokie CPA, niski QS).
- Nie używaj innych emoji ani znaków zastępczych. Każdy bullet musi mieć dokładnie 🟢 lub 🔴 jako pierwszy znak po `-` lub `*`.

Przykłady:
- 🟢 BRAND `actio voip` PHRASE: 4 konwersje za 5.93 zł = CPA 1.48 zł — **rekord tygodnia**.
- 🔴 SEARCH_VOIP_PL_ALL: 8 klików / 15.76 zł / 0 konwersji — pali budżet bez efektu.

## Rekomendacje
Lista 1-5 konkretnych akcji do podjęcia DZIŚ. Każda akcja musi być jednoznaczna (np. "dodaj frazę X jako negative w kampanii Y", nie "rozważ optymalizację"). Priorytetyzuj wpływ na realne leady (`generate_lead` z Polski), nie fake metryki.

NIE pisz wstępu ani podsumowania. Zacznij od `## Daily digest`. Krótko, rzeczowo, bez emoji.

DANE:

### GA4 — konwersje per źródło/medium (ostatnie 7 dni)
{ga4_conversions_by_source}

### GA4 — konwersje per źródło/medium (poprzedni tydzień, 8-14 dni temu, do porównania w-o-w)
{ga4_conversions_by_source_prev}

### GA4 — leady (`generate_lead`) per landing+source (7 dni)
{ga4_leads_per_landing}

### Google Ads — kampanie (ostatnie 7 dni, kolumny is_pct/lost_budget_pct/lost_rank_pct = Lost IS %)
{ads_campaigns_7d}

### Google Ads — kampanie (poprzedni tydzień, 8-14 dni temu, do porównania w-o-w)
{ads_campaigns_7d_prev}

### Google Ads — performance assetów (sitelinks/callouts/call ext, 7 dni)
{ads_assets_perf_7d}

### Kampania SEARCH_COMPETITOR_PL — szczegóły (7 dni)

Podkampania bidująca na keywordy konkurentów (welyo/halonet/plfon/zadarma itd.). Treść reklamy bez nazw konkurentów (Google policy). W raporcie omów osobno: ROI tej kampanii, jakie konkurenty generują kliki, jakie search terms wpadają (sygnał intencji rynku).

**Performance kampanii:**
{competitor_campaign_7d}

**Keywordy COMPETITOR — co generuje kliki:**
{competitor_keywords_7d}

**Search terms — co realnie wpisują ludzie:**
{competitor_search_terms_7d}

### Google Ads — top 20 search terms wg kosztu (7 dni)
{ads_search_terms_top20_7d}

### Google Ads — top 20 keywords (7 dni)
{ads_keywords_7d}

### GSC — top 10 zapytań organic (7 dni)
{gsc_queries_7d}

### GSC — top 10 stron landing (7 dni)
{gsc_pages_7d}
"""


def run_all_syncs() -> dict[str, str]:
    db_path = _env("DB_PATH")
    ga4_property = _env("GA4_PROPERTY_ID", "")
    ads_customer = _env("GOOGLE_ADS_CUSTOMER_ID", "")
    results: dict[str, str] = {}
    db.init_db(db_path)

    try:
        rows = ga4.fetch_last_7_days(ga4_property)
        results["ga4"] = f"OK ({db.upsert_rows(db_path, rows)} wierszy)"
    except Exception as e:
        results["ga4"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows = ga4.fetch_landing_conversions_last_7_days(ga4_property)
        results["ga4_landing"] = f"OK ({db.upsert_landing_conversions(db_path, rows)} wierszy)"
    except Exception as e:
        results["ga4_landing"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows, sites = gsc.fetch_all_sites_last_7_days()
        results["gsc"] = f"OK ({db.upsert_gsc_rows(db_path, rows)} wierszy, {len(sites)} property)"
    except Exception as e:
        results["gsc"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows = ads.fetch_campaigns_last_7_days(ads_customer)
        results["ads_campaigns"] = f"OK ({db.upsert_ads_campaign_rows(db_path, rows)} wierszy)"
    except Exception as e:
        results["ads_campaigns"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows = ads.fetch_keywords_last_30_days(ads_customer)
        results["ads_keywords"] = f"OK ({db.upsert_ads_keyword_rows(db_path, rows)} wierszy)"
    except Exception as e:
        results["ads_keywords"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows = ads.fetch_search_terms_last_30_days(ads_customer)
        results["ads_search_terms"] = f"OK ({db.upsert_ads_search_term_rows(db_path, rows)} wierszy)"
    except Exception as e:
        results["ads_search_terms"] = f"ERROR: {type(e).__name__}: {e}"

    return results


def collect_data_summary() -> dict[str, str]:
    db_path = _env("DB_PATH")
    ads_customer = _env("GOOGLE_ADS_CUSTOMER_ID", "")

    ga4_df = db.fetch_history(db_path, days=7)
    ga4_prev_df = db.fetch_history(db_path, days=7, offset_days=7)
    landing_df = db.fetch_landing_conversions(db_path, days=7, top=20)
    ads_df = db.fetch_ads_campaigns(db_path, days=7)
    ads_prev_df = db.fetch_ads_campaigns(db_path, days=7, offset_days=7)
    waste_df = db.fetch_ads_search_terms(db_path, days=7, top=20)
    kw_df = db.fetch_ads_keywords(db_path, days=7).head(20)
    gsc_q = db.fetch_gsc_top_queries(db_path, days=7, top=10)
    gsc_p = db.fetch_gsc_top_pages(db_path, days=7, top=10)

    # COMPETITOR — osobna sekcja
    competitor_camp_df = ads_df[ads_df["campaign_name"] == "SEARCH_COMPETITOR_PL"]
    all_kw = db.fetch_ads_keywords(db_path, days=7)
    competitor_kw_df = all_kw[all_kw["campaign_name"] == "SEARCH_COMPETITOR_PL"]
    all_terms = db.fetch_ads_search_terms(db_path, days=7, top=200)
    competitor_terms_df = all_terms[all_terms["campaign_name"] == "SEARCH_COMPETITOR_PL"].head(20)

    # A: live state z Ads API (eliminuje halucynacje)
    try:
        live_state = ads.fetch_live_account_state(ads_customer)
    except Exception as e:
        live_state = f"(błąd pobierania live state: {type(e).__name__}: {e})"

    # C: customer assets performance
    try:
        assets_perf = ads.fetch_customer_assets_perf(ads_customer)
        assets_md = pd.DataFrame(assets_perf).to_markdown(index=False) if assets_perf else "(brak danych)"
    except Exception as e:
        assets_md = f"(błąd: {type(e).__name__}: {e})"

    def _md(df) -> str:
        return df.to_markdown(index=False) if not df.empty else "(brak danych)"

    return {
        "date": datetime.date.today().isoformat(),
        "live_account_state": live_state,
        "ga4_conversions_by_source": _md(ga4_df),
        "ga4_conversions_by_source_prev": _md(ga4_prev_df),
        "ga4_leads_per_landing": _md(landing_df),
        "ads_campaigns_7d": _md(ads_df),
        "ads_campaigns_7d_prev": _md(ads_prev_df),
        "ads_search_terms_top20_7d": _md(waste_df),
        "ads_keywords_7d": _md(kw_df),
        "ads_assets_perf_7d": assets_md,
        "competitor_campaign_7d": _md(competitor_camp_df),
        "competitor_keywords_7d": _md(competitor_kw_df),
        "competitor_search_terms_7d": _md(competitor_terms_df),
        "gsc_queries_7d": _md(gsc_q),
        "gsc_pages_7d": _md(gsc_p),
    }


def call_openrouter(prompt: str) -> str:
    r = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {_env('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://actio.pl",
            "X-Title": "Actio Marketing CMO-layer",
        },
        json={
            "model": _env("OPENROUTER_MODEL", "anthropic/claude-opus-4.7"),
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=180.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _build_report_content(date_iso: str, report_md: str, sync_status: dict) -> str:
    sync_lines = "\n".join(f"- **{k}**: {v}" for k, v in sync_status.items())
    return (
        f"---\n"
        f"date: {date_iso}\n"
        f"type: marketing-report\n"
        f"project: actio-marketing\n"
        f"---\n\n"
        f"# Raport Actio Marketing — {date_iso}\n\n"
        f"## Sync status\n{sync_lines}\n\n"
        f"{report_md}\n"
    )


def save_to_md_reports(date_iso: str, report_md: str, sync_status: dict) -> str:
    """Zapisuje raport do katalogu /md-reports/ (deployment server)."""
    reports_dir = pathlib.Path(_env("MD_REPORTS_DIR"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{date_iso}-actio-marketing-report.md"
    path.write_text(_build_report_content(date_iso, report_md, sync_status), encoding="utf-8")
    return str(path)


def save_to_obsidian(date_iso: str, report_md: str, sync_status: dict) -> str:
    """Zapisuje raport do Obsidian vault przez obsidian CLI (tryb lokalny)."""
    reports_path = _env("OBSIDIAN_REPORTS_PATH", "projects/actio-marketing-reports")
    path = f"{reports_path}/{date_iso}.md"
    content = _build_report_content(date_iso, report_md, sync_status)
    subprocess.run(
        ["obsidian", "create", f"path={path}", f"content={content}"],
        check=True,
        capture_output=True,
    )
    return path


def save_report(date_iso: str, report_md: str, sync_status: dict) -> str:
    """Wybiera backend zapisu: jeśli MD_REPORTS_DIR ustawione → md-reports, inaczej Obsidian."""
    if os.environ.get("MD_REPORTS_DIR"):
        return save_to_md_reports(date_iso, report_md, sync_status)
    return save_to_obsidian(date_iso, report_md, sync_status)


def send_pushover(title: str, message: str, url: str | None = None) -> None:
    payload = {
        "token": _env("PUSHOVER_API_TOKEN"),
        "user": _env("PUSHOVER_USER_KEY"),
        "title": title,
        "message": message[:1024],
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "Otwórz w Obsidianie"
    r = httpx.post("https://api.pushover.net/1/messages.json", data=payload, timeout=15.0)
    r.raise_for_status()


def _build_obsidian_url(vault_path: str) -> str:
    vault_name = _env("OBSIDIAN_VAULT_NAME", "vault")
    file_no_ext = vault_path[:-3] if vault_path.endswith(".md") else vault_path
    return (
        f"obsidian://open?vault={urllib.parse.quote(vault_name)}"
        f"&file={urllib.parse.quote(file_no_ext)}"
    )


def _short_summary(report_md: str) -> str:
    """Wyciąga 1-2 pierwsze linie z sekcji Daily digest dla notyfikacji push."""
    lines = report_md.splitlines()
    digest: list[str] = []
    in_digest = False
    for line in lines:
        if line.strip().startswith("## Daily digest"):
            in_digest = True
            continue
        if in_digest and line.strip().startswith("##"):
            break
        if in_digest and line.strip():
            digest.append(line.strip())
    return " ".join(digest)[:400] if digest else report_md[:400]


def generate_report() -> dict:
    sync_status = run_all_syncs()
    data = collect_data_summary()
    prompt = REPORT_PROMPT.format(**data)
    report_md = call_openrouter(prompt)
    vault_path = save_report(data["date"], report_md, sync_status)
    if os.environ.get("MD_REPORTS_DIR"):
        base = os.environ.get("CHAINLIT_BASE_URL", "").rstrip("/")
        report_url = f"{base}/raporty?file={pathlib.Path(vault_path).name}" if base else vault_path
    else:
        report_url = _build_obsidian_url(vault_path)
    send_pushover(
        title=f"Actio raport {data['date']}",
        message=_short_summary(report_md),
        url=report_url,
    )
    triggered_alerts = alerts.check_thresholds(_env("DB_PATH"))
    email_result = email_sender.send_report_email(
        date_iso=data["date"],
        report_md=report_md,
        sync_status=sync_status,
        alerts=triggered_alerts,
        obsidian_url=report_url,
    )
    return {
        "date": data["date"],
        "report_md": report_md,
        "vault_path": vault_path,
        "obsidian_url": report_url,
        "sync_status": sync_status,
        "alerts": triggered_alerts,
        "email": email_result,
    }


if __name__ == "__main__":
    result = generate_report()
    print(f"\n=== Sync ===")
    for k, v in result["sync_status"].items():
        print(f"  {k}: {v}")
    print(f"\n=== Zapisano ===\n  {result['vault_path']}")
    print(f"  {result['obsidian_url']}")
    print(f"\n=== Raport ===\n{result['report_md']}")
