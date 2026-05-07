"""Google Ads API wrapper — pobiera dzienne metryki kampanii."""
from __future__ import annotations

import os
from collections import defaultdict

from google.ads.googleads.client import GoogleAdsClient


def _client() -> GoogleAdsClient:
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def fetch_live_account_state(customer_id: str) -> str:
    """Aktualny stan konta dla prompt CMO — eliminuje halucynacje modelu.

    Pyta API LIVE o:
    - Aktywne kampanie + budżety + bid strategy
    - Aktywne negatywy per kampania (top 5 najnowszych)
    - Daty kiedy kampanie zostały utworzone

    Zwraca markdown gotowy do wstawienia w prompt.
    """
    client = _client()
    ga = client.get_service("GoogleAdsService")

    # 1. Aktywne kampanie z budżetami
    q = """
        SELECT campaign.name, campaign.status,
               campaign_budget.amount_micros, campaign.bidding_strategy_type
        FROM campaign
        WHERE campaign.status = 'ENABLED'
        ORDER BY campaign.name
    """
    camps_md = ["| Kampania | Budżet | Bidding |", "|---|---|---|"]
    camp_names = []
    for r in ga.search(customer_id=customer_id, query=q):
        bud = r.campaign_budget.amount_micros / 1e6 if r.campaign_budget.amount_micros else 0
        camps_md.append(f"| {r.campaign.name} | {bud:.0f} zł/d | {r.campaign.bidding_strategy_type.name} |")
        camp_names.append(r.campaign.name)

    # 2. Negatywy per kampania
    q = """
        SELECT campaign.name, campaign_criterion.keyword.text,
               campaign_criterion.keyword.match_type
        FROM campaign_criterion
        WHERE campaign_criterion.negative = TRUE
          AND campaign_criterion.type = 'KEYWORD'
          AND campaign.status = 'ENABLED'
    """
    negs = defaultdict(list)
    for r in ga.search(customer_id=customer_id, query=q):
        mt = r.campaign_criterion.keyword.match_type.name[0]
        negs[r.campaign.name].append(f"{r.campaign_criterion.keyword.text}[{mt}]")

    negs_md = ["", "**Aktywne negatywy per kampania:**"]
    for cn in camp_names:
        kws = sorted(negs.get(cn, []))
        if kws:
            negs_md.append(f"- **{cn}** ({len(kws)}): {', '.join(kws[:25])}{' ...' if len(kws) > 25 else ''}")

    return "\n".join(camps_md) + "\n" + "\n".join(negs_md)


def fetch_customer_assets_perf(customer_id: str) -> list[dict]:
    """Performance assetów (sitelink/callout/call) na poziomie konta — ostatnie 7 dni."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    q = """
        SELECT customer_asset.field_type,
               asset.name,
               asset.sitelink_asset.link_text,
               asset.callout_asset.callout_text,
               asset.call_asset.phone_number,
               metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM customer_asset
        WHERE customer_asset.status = 'ENABLED'
          AND segments.date DURING LAST_7_DAYS
    """
    rows = []
    for r in ga.search(customer_id=customer_id, query=q):
        ft = r.customer_asset.field_type.name
        if ft == "SITELINK":
            label = r.asset.sitelink_asset.link_text or r.asset.name
        elif ft == "CALLOUT":
            label = r.asset.callout_asset.callout_text
        elif ft == "CALL":
            label = r.asset.call_asset.phone_number
        else:
            label = r.asset.name or "(unnamed)"
        rows.append({
            "field_type": ft,
            "asset": label,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost_pln": round(r.metrics.cost_micros / 1e6, 2),
        })
    return rows


def fetch_campaigns_last_7_days(customer_id: str) -> list[dict]:
    """Per (date, campaign) — clicks, impressions, cost, conversions, value."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = """
        SELECT segments.date,
               campaign.id, campaign.name, campaign.status,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value,
               metrics.search_impression_share,
               metrics.search_budget_lost_impression_share,
               metrics.search_rank_lost_impression_share,
               metrics.search_top_impression_share,
               metrics.search_absolute_top_impression_share
        FROM campaign
        WHERE segments.date DURING LAST_7_DAYS
    """
    rows: list[dict] = []
    for r in ga.search(customer_id=customer_id, query=query):
        m = r.metrics
        rows.append({
            "date": r.segments.date,
            "customer_id": customer_id,
            "campaign_id": str(r.campaign.id),
            "campaign_name": r.campaign.name,
            "status": r.campaign.status.name,
            "clicks": m.clicks,
            "impressions": m.impressions,
            "cost": m.cost_micros / 1_000_000,
            "conversions": m.conversions,
            "conv_value": m.conversions_value,
            "impression_share": m.search_impression_share or 0.0,
            "budget_lost_is": m.search_budget_lost_impression_share or 0.0,
            "rank_lost_is": m.search_rank_lost_impression_share or 0.0,
            "top_is": m.search_top_impression_share or 0.0,
            "absolute_top_is": m.search_absolute_top_impression_share or 0.0,
        })
    return rows


def fetch_keywords_last_30_days(customer_id: str) -> list[dict]:
    """Per (date, campaign, ad_group, keyword) — clicks, impressions, cost, conv, QS."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = """
        SELECT segments.date,
               campaign.id, campaign.name,
               ad_group.id, ad_group.name,
               ad_group_criterion.criterion_id,
               ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status,
               ad_group_criterion.quality_info.quality_score,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value
        FROM keyword_view
        WHERE segments.date DURING LAST_30_DAYS
    """
    rows: list[dict] = []
    for r in ga.search(customer_id=customer_id, query=query):
        rows.append({
            "date": r.segments.date,
            "customer_id": customer_id,
            "campaign_id": str(r.campaign.id),
            "campaign_name": r.campaign.name,
            "ad_group_id": str(r.ad_group.id),
            "ad_group_name": r.ad_group.name,
            "criterion_id": str(r.ad_group_criterion.criterion_id),
            "keyword": r.ad_group_criterion.keyword.text,
            "match_type": r.ad_group_criterion.keyword.match_type.name,
            "status": r.ad_group_criterion.status.name,
            "quality_score": r.ad_group_criterion.quality_info.quality_score or 0,
            "clicks": r.metrics.clicks,
            "impressions": r.metrics.impressions,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
            "conv_value": r.metrics.conversions_value,
        })
    return rows


def fetch_search_terms_last_30_days(customer_id: str) -> list[dict]:
    """Real search terms triggering ads (search_term_view) — date × campaign × term."""
    client = _client()
    ga = client.get_service("GoogleAdsService")
    query = """
        SELECT segments.date,
               campaign.id, campaign.name,
               ad_group.id, ad_group.name,
               search_term_view.search_term,
               search_term_view.status,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value
        FROM search_term_view
        WHERE segments.date DURING LAST_30_DAYS
    """
    rows: list[dict] = []
    for r in ga.search(customer_id=customer_id, query=query):
        rows.append({
            "date": r.segments.date,
            "customer_id": customer_id,
            "campaign_id": str(r.campaign.id),
            "campaign_name": r.campaign.name,
            "ad_group_id": str(r.ad_group.id),
            "ad_group_name": r.ad_group.name,
            "search_term": r.search_term_view.search_term,
            "status": r.search_term_view.status.name,
            "clicks": r.metrics.clicks,
            "impressions": r.metrics.impressions,
            "cost": r.metrics.cost_micros / 1_000_000,
            "conversions": r.metrics.conversions,
            "conv_value": r.metrics.conversions_value,
        })
    return rows
