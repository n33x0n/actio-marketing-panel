"""Smoke test — czy Google Ads API odpowiada dla konta Actio.

Użycie:
    uv run python scripts/ads_smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys

from google.ads.googleads.client import GoogleAdsClient


def main() -> None:
    mcp = json.load(open(".mcp.json"))["mcpServers"]["actio-marketing"]["env"]
    config = {
        "developer_token": mcp["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": mcp["GOOGLE_ADS_OAUTH_CLIENT_ID"],
        "client_secret": mcp["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
        "refresh_token": mcp["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": mcp["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    }
    customer_id = mcp["GOOGLE_ADS_CUSTOMER_ID"]

    client = GoogleAdsClient.load_from_dict(config)
    ga = client.get_service("GoogleAdsService")

    query = """
        SELECT campaign.id, campaign.name, campaign.status,
               metrics.clicks, metrics.impressions, metrics.cost_micros
        FROM campaign
        WHERE segments.date DURING LAST_7_DAYS
        ORDER BY metrics.cost_micros DESC
    """
    print(f"Konto: {customer_id} (login_customer: {mcp['GOOGLE_ADS_LOGIN_CUSTOMER_ID']})")
    print("Kampanie — ostatnie 7 dni:\n")
    rows = ga.search(customer_id=customer_id, query=query)
    for r in rows:
        cost = r.metrics.cost_micros / 1_000_000
        print(
            f"  {r.campaign.id:>12} | {r.campaign.status.name:>8} | "
            f"clicks={r.metrics.clicks:>5} impr={r.metrics.impressions:>6} "
            f"cost={cost:>7.2f} zł | {r.campaign.name}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
