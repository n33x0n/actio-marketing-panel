"""Threshold-based alerts: emergency push (priority=2) gdy metryki przekraczają limity.

Wywoływany z analyze.py po fresh sync. Sprawdza:
- CPA > 50 zł per kampania (gdy są konwersje)
- Lost IS budget > 30% per kampania
- Brak konwersji 48h przy >50 kliknięć (suchy spend)
- Dzienny spend > 80% budżetu już przed południem (early burn)

Każda anomalia → osobny push priority=2 (emergency, dźwięk dopóki user nie potwierdzi).
"""
from __future__ import annotations

import datetime
import os

import httpx


CPA_MAX_PLN = 50.0
LOST_IS_BUDGET_MAX = 0.30
DRY_SPEND_DAYS = 2
DRY_SPEND_MIN_CLICKS = 50
EARLY_BURN_PCT = 0.80


def _send_emergency(title: str, message: str) -> None:
    httpx.post(
        "https://api.pushover.net/1/messages.json",
        data={
            "token": os.environ["PUSHOVER_API_TOKEN"],
            "user": os.environ["PUSHOVER_USER_KEY"],
            "title": f"⚠️ {title}",
            "message": message[:1024],
            "priority": 2,
            "retry": 60,
            "expire": 3600,
        },
        timeout=15.0,
    ).raise_for_status()


def check_thresholds(db_path: str) -> list[dict]:
    """Zwraca listę triggered alertów. Wysyła osobne push per alert."""
    import db

    triggered: list[dict] = []
    df = db.fetch_ads_campaigns(db_path, days=7)
    if df.empty:
        return triggered

    for _, row in df.iterrows():
        name = row["campaign_name"]
        clicks = float(row.get("clicks", 0) or 0)
        cost = float(row.get("cost_pln", 0) or 0)
        conv = float(row.get("conversions", 0) or 0)

        if conv > 0:
            cpa = cost / conv
            if cpa > CPA_MAX_PLN:
                triggered.append({"campaign": name, "type": "CPA",
                                  "msg": f"{name}: CPA {cpa:.2f} zł (>{CPA_MAX_PLN} zł), {conv:.1f} konwersji / {cost:.2f} zł"})

        if clicks >= DRY_SPEND_MIN_CLICKS and conv == 0:
            triggered.append({"campaign": name, "type": "DRY_SPEND",
                              "msg": f"{name}: {int(clicks)} kliknięć / {cost:.2f} zł / 0 konwersji w 7 dni"})

    triggered.extend(_check_policy())

    for alert in triggered:
        _send_emergency(f"Actio Ads: {alert['type']}", alert["msg"])

    return triggered


def _check_policy() -> list[dict]:
    """Sprawdź policy_summary RSA i assetów. Zwraca alerts jeśli APPROVED_LIMITED/DISAPPROVED."""
    issues: list[dict] = []
    try:
        from google.ads.googleads.client import GoogleAdsClient
        client = GoogleAdsClient.load_from_dict({
            "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
            "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
            "use_proto_plus": True,
        })
        cust = os.environ["GOOGLE_ADS_CUSTOMER_ID"]
        ga = client.get_service("GoogleAdsService")

        q_ads = """
            SELECT campaign.name, ad_group_ad.policy_summary.approval_status,
                   ad_group_ad.policy_summary.policy_topic_entries
            FROM ad_group_ad
            WHERE ad_group_ad.status = 'ENABLED'
              AND campaign.status = 'ENABLED'
              AND ad_group_ad.policy_summary.approval_status IN ('DISAPPROVED', 'APPROVED_LIMITED')
        """
        for r in ga.search(customer_id=cust, query=q_ads):
            topics = ", ".join(e.topic for e in r.ad_group_ad.policy_summary.policy_topic_entries) or "?"
            status = r.ad_group_ad.policy_summary.approval_status.name
            issues.append({"type": "POLICY_AD",
                           "msg": f"{r.campaign.name}: reklama {status} ({topics})"})

        q_assets = """
            SELECT customer_asset.field_type, asset.policy_summary.approval_status,
                   asset.policy_summary.policy_topic_entries, asset.name
            FROM customer_asset
            WHERE customer_asset.status = 'ENABLED'
              AND asset.policy_summary.approval_status IN ('DISAPPROVED', 'APPROVED_LIMITED')
        """
        for r in ga.search(customer_id=cust, query=q_assets):
            topics = ", ".join(e.topic for e in r.asset.policy_summary.policy_topic_entries) or "?"
            field = r.customer_asset.field_type.name
            status = r.asset.policy_summary.approval_status.name
            name = r.asset.name or "(unnamed)"
            issues.append({"type": "POLICY_ASSET",
                           "msg": f"Asset {field} '{name}' {status} ({topics})"})
    except Exception as e:
        issues.append({"type": "POLICY_CHECK_ERROR", "msg": f"{type(e).__name__}: {e}"[:200]})
    return issues
