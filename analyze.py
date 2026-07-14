"""CMO-layer — fresh sync wszystkich źródeł + analiza Opus 4.7 (przez OpenRouter)
+ zapis raportu do Obsidiana + push na telefon."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
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

from brand_config import get_brand


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
        rows = ga4.fetch_lead_events_breakdown_last_7_days(ga4_property)
        results["ga4_lead_events"] = f"OK ({db.upsert_lead_events(db_path, rows)} wierszy)"
    except Exception as e:
        results["ga4_lead_events"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows, sites = gsc.fetch_all_sites_last_7_days()
        results["gsc"] = f"OK ({db.upsert_gsc_rows(db_path, rows)} wierszy, {len(sites)} property)"
    except Exception as e:
        results["gsc"] = f"ERROR: {type(e).__name__}: {e}"

    try:
        rows = gsc.fetch_all_sites_totals()
        results["gsc_totals"] = f"OK ({db.upsert_gsc_totals(db_path, rows)} dni)"
    except Exception as e:
        results["gsc_totals"] = f"ERROR: {type(e).__name__}: {e}"

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

    if get_brand().cloudflare_enabled:
        try:
            import cloudflare
            results.update(cloudflare.sync_all(db_path))
        except Exception as e:
            results["cloudflare"] = f"ERROR: {type(e).__name__}: {e}"

    return results


def _load_cmo_context() -> str:
    """Żywy dziennik incydentów/decyzji (cmo_context.md obok skryptu).

    Aktualizowany przy każdej zmianie na koncie / decyzji właściciela —
    dzięki temu raport nie rekomenduje rzeczy już odrzuconych i nie czyta
    artefaktów pomiaru jako spadków wydajności.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), get_brand().context_file)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "(brak pliku cmo_context.md — brak kontekstu incydentów/decyzji)"


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
    gsc_tot = db.fetch_gsc_totals(db_path, days=7)

    # Lead type breakdown (form vs phone) — z GTM custom dimensions
    lead_type_df = db.fetch_lead_events_breakdown(db_path, days=7, group_by="lead_type")
    lead_form_id_df = db.fetch_lead_events_breakdown(db_path, days=7, group_by="form_id")
    lead_phone_df = db.fetch_lead_events_breakdown(db_path, days=7, group_by="phone_number")

    # COMPETITOR — osobna sekcja
    competitor_camp_df = ads_df[ads_df["campaign_name"] == get_brand().competitor_campaign]
    all_kw = db.fetch_ads_keywords(db_path, days=7)
    competitor_kw_df = all_kw[all_kw["campaign_name"] == get_brand().competitor_campaign]
    all_terms = db.fetch_ads_search_terms(db_path, days=7, top=200)
    competitor_terms_df = all_terms[all_terms["campaign_name"] == get_brand().competitor_campaign].head(20)

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
        "cmo_context": _load_cmo_context(),
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
        "gsc_totals_7d": _md(gsc_tot),
        "gsc_queries_7d": _md(gsc_q),
        "gsc_pages_7d": _md(gsc_p),
        "lead_type_breakdown_7d": _md(lead_type_df),
        "lead_form_id_breakdown_7d": _md(lead_form_id_df),
        "lead_phone_number_breakdown_7d": _md(lead_phone_df),
    }


def call_openrouter(prompt: str) -> str:
    from langfuse.openai import openai
    client = openai.OpenAI(
        api_key=_env("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": get_brand().openrouter_referer,
            "X-Title": get_brand().openrouter_title,
        },
        timeout=180.0,
    )
    def _call(model: str) -> str | None:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # Fable 5 ma zawsze wlaczony thinking (liczy sie do completion) - 16k daje zapas na raport
            max_tokens=16000,
            extra_body={"provider": {"data_collection": "deny"}},
            name="daily_report_cmo",
            metadata={"source": "analyze.py", "use_case": "daily_report"},
        )
        return resp.choices[0].message.content

    primary = _env("OPENROUTER_MODEL", "anthropic/claude-fable-5")
    fallback = _env("OPENROUTER_FALLBACK_MODEL", "anthropic/claude-opus-4.8")
    try:
        out = _call(primary)
        if out and out.strip():
            return out
        print(f"[call_openrouter] pusty output z {primary} - fallback na {fallback}")
    except Exception as e:
        print(f"[call_openrouter] {primary} padl ({type(e).__name__}: {e}) - fallback na {fallback}")
    return _call(fallback)


def _build_report_content(date_iso: str, report_md: str, sync_status: dict) -> str:
    sync_lines = "\n".join(f"- **{k}**: {v}" for k, v in sync_status.items())
    return (
        f"---\n"
        f"date: {date_iso}\n"
        f"type: marketing-report\n"
        f"project: {get_brand().report_slug}\n"
        f"---\n\n"
        f"# Raport {get_brand().name} Marketing — {date_iso}\n\n"
        f"## Sync status\n{sync_lines}\n\n"
        f"{report_md}\n"
    )


def panel_view(report_md: str) -> str:
    """Filtr raportu dla panelu: usuwa sekcję Rekomendacje + zostawia tylko pozytywne (🟢) anomalie.

    Pełny raport (z 🔴 + Rekomendacjami) zostaje w MD_FULL_DIR i email do CMO.
    Panel view trafia do MD_REPORTS_DIR i jest wyświetlany w Chainlit.
    """
    md = re.sub(r"\n+##\s*Rekomendacje.*", "", report_md, flags=re.DOTALL).rstrip() + "\n"
    # GEO / AI Share of Voice — sekcja tylko dla CMO; usun z wersji panel (Hubert).
    md = re.sub(r"\n+##\s*GEO.*", "", md, flags=re.DOTALL).rstrip() + "\n"

    lines = md.splitlines()
    out: list[str] = []
    in_anomalies = False
    has_anomalies_section = False
    kept_positive = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            in_anomalies = stripped.lower().startswith("## anomalie")
            if in_anomalies:
                has_anomalies_section = True
            out.append(line)
            continue
        if in_anomalies and re.match(r"^\s*[-*]\s+", line):
            content = re.sub(r"^\s*[-*]\s+", "", line)
            if content.lstrip().startswith("🟢"):
                out.append(line)
                kept_positive += 1
            continue
        out.append(line)

    result = "\n".join(out)
    if has_anomalies_section and kept_positive == 0:
        result = re.sub(
            r"(##\s*Anomalie[^\n]*)(\n|$)",
            r"\1\n\n_Brak pozytywnych anomalii w tym okresie._\n",
            result,
            count=1,
        )
    return result


def save_to_md_reports(date_iso: str, report_md: str, sync_status: dict) -> str:
    """Zapisuje raport do dwóch katalogów:
    - MD_FULL_DIR: pełny raport (z 🔴 i Rekomendacjami) — używane przez email + push
    - MD_REPORTS_DIR: panel view (bez Rekomendacji, tylko 🟢 anomalie) — widoczny w Chainlit

    Zwraca path do PEŁNEGO raportu (do linkowania w mailu).
    """
    full_content = _build_report_content(date_iso, report_md, sync_status)
    panel_content = _build_report_content(date_iso, panel_view(report_md), sync_status)

    full_dir = pathlib.Path(_env("MD_FULL_DIR", _env("MD_REPORTS_DIR") + "-full"))
    full_dir.mkdir(parents=True, exist_ok=True)
    full_path = full_dir / f"{date_iso}-{get_brand().report_slug}-report.md"
    full_path.write_text(full_content, encoding="utf-8")

    panel_dir = pathlib.Path(_env("MD_REPORTS_DIR"))
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_path = panel_dir / f"{date_iso}-{get_brand().report_slug}-report.md"
    panel_path.write_text(panel_content, encoding="utf-8")

    return str(full_path)


def save_to_obsidian(date_iso: str, report_md: str, sync_status: dict) -> str:
    """Zapisuje raport do Obsidian vault przez obsidian CLI (tryb lokalny)."""
    reports_path = _env("OBSIDIAN_REPORTS_PATH", get_brand().obsidian_reports_path)
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


def send_pushover(title: str, message: str, url: str | None = None, user_key: str | None = None) -> None:
    payload = {
        "token": _env("PUSHOVER_API_TOKEN"),
        "user": user_key or _env("PUSHOVER_USER_KEY"),
        "title": title,
        "message": message[:1024],
    }
    if url:
        payload["url"] = url
        payload["url_title"] = "Otwórz panel"
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


def _panel_pushover_summary(report_md: str) -> str:
    """Wersja push dla grupy panel (Hubert): Daily digest + 🟢 anomalie."""
    panel_md = panel_view(report_md)
    digest = _short_summary(panel_md)

    # Wyciągnij 🟢 anomalie
    positive: list[str] = []
    in_anomalies = False
    for line in panel_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            in_anomalies = stripped.lower().startswith("## anomalie")
            continue
        if in_anomalies and re.match(r"^\s*[-*]\s+", line):
            content = re.sub(r"^\s*[-*]\s+", "", line).strip()
            if content.startswith("🟢"):
                positive.append("• " + content[1:].strip())  # bez emoji w push (oszczędność znaków)

    out = digest
    if positive:
        out += "\n\n🟢 Pozytywy:\n" + "\n".join(positive[:3])
    return out[:1024]


def generate_report() -> dict:
    sync_status = run_all_syncs()
    data = collect_data_summary()
    prompt = get_brand().report_prompt.format(**data)
    report_md = call_openrouter(prompt)
    # Sekcja GEO / AI Share of Voice — tylko raport CMO (panel_view ja usuwa -> Hubert nie dostaje).
    try:
        import geo_report
        report_md = report_md.rstrip() + "\n\n" + geo_report.build_report(as_section=True)
    except Exception as e:
        print(f"geo_report append error: {type(e).__name__}: {e}")
    if get_brand().cloudflare_enabled:
        try:
            import cloudflare
            _cf = cloudflare.build_section()
            if _cf:
                report_md = report_md.rstrip() + "\n\n" + _cf
        except Exception as e:
            print(f"cloudflare section error: {type(e).__name__}: {e}")
    vault_path = save_report(data["date"], report_md, sync_status)
    if os.environ.get("MD_REPORTS_DIR"):
        base = os.environ.get("CHAINLIT_BASE_URL", "").rstrip("/")
        report_url = f"{base}/raporty?file={pathlib.Path(vault_path).name}" if base else vault_path
    else:
        report_url = _build_obsidian_url(vault_path)
    # Push #1 — Tomek (CMO): pełna wersja Daily digest (skip jeśli PUSHOVER_USER_KEY niemożna)
    if os.environ.get("PUSHOVER_USER_KEY"):
        send_pushover(
            title=f"{get_brand().name} raport {data['date']}",
            message=_short_summary(report_md),
            url=report_url,
        )

    # Push #2 — grupa PANEL (Hubert + ew. inni): wersja panel (Daily digest + 🟢 anomalie)
    panel_keys = [k.strip() for k in os.environ.get("PUSHOVER_USER_KEY_PANEL", "").split(",") if k.strip()]
    if panel_keys:
        panel_summary = _panel_pushover_summary(report_md)
        for uk in panel_keys:
            try:
                send_pushover(
                    title=f"{get_brand().name} raport {data['date']}",
                    message=panel_summary,
                    url=report_url,
                    user_key=uk,
                )
            except Exception as e:
                print(f"pushover panel error for {uk[:6]}...: {e}")

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
