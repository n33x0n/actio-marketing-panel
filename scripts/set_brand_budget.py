"""Ustaw budget BRAND kampanii. Wywołanie: `uv run python scripts/set_brand_budget.py 60`."""
from __future__ import annotations

import json
import os
import pathlib
import sys


def _load_env() -> None:
    p = pathlib.Path(__file__).parent.parent / ".mcp.json"
    if p.exists():
        cfg = json.loads(p.read_text())
        for k, v in cfg["mcpServers"]["actio-marketing"]["env"].items():
            os.environ.setdefault(k, v)


def main(amount_pln: float) -> None:
    _load_env()
    from google.ads.googleads.client import GoogleAdsClient
    client = GoogleAdsClient.load_from_dict({
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }, version="v22")
    cust = os.environ["GOOGLE_ADS_CUSTOMER_ID"]
    ga = client.get_service("GoogleAdsService")

    q = "SELECT campaign_budget.resource_name FROM campaign WHERE campaign.name='SEARCH_BRAND_PL_DESKTOP'"
    budget_rn = next(iter(ga.search(customer_id=cust, query=q))).campaign_budget.resource_name

    bsvc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    op.update.resource_name = budget_rn
    op.update.amount_micros = int(amount_pln * 1_000_000)
    op.update_mask.paths.append("amount_micros")
    bsvc.mutate_campaign_budgets(customer_id=cust, operations=[op])
    print(f"OK: BRAND budget = {amount_pln:.2f} zł/d")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: set_brand_budget.py <amount_pln>")
    main(float(sys.argv[1]))
