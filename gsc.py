"""Google Search Console Data API wrapper — date × query × page per site."""
from __future__ import annotations

from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build


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


def fetch_all_sites_last_7_days() -> tuple[list[dict], list[str]]:
    """Ostatnie 7 dni dla wszystkich property do których SA ma dostęp.

    Returns:
        (rows, sites) — wiersze gotowe dla db.upsert_gsc_rows + lista
        przepytanych site_url.
    """
    sites = list_sites()
    all_rows: list[dict] = []
    processed: list[str] = []

    for site in sites:
        rows = fetch_last_7_days(site["site_url"])
        all_rows.extend(rows)
        processed.append(site["site_url"])

    return all_rows, processed
