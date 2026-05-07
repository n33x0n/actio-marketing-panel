"""GA4 Data API wrapper — pobiera konwersje za ostatnie 7 dni."""
from __future__ import annotations

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    RunReportRequest,
)

EXCLUDED_COUNTRIES = ("Singapore", "United States")


def _iso_date(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def fetch_last_7_days(property_id: str) -> list[dict]:
    """Sessions / users / conversions per (date, sessionSourceMedium) z ostatnich 7 dni.

    Zwraca listę dictów gotową dla db.upsert_rows:
        {"date": "2025-04-23", "source_medium": "google / cpc",
         "sessions": 123, "users": 98, "conversions": 4.2}
    """
    client = BetaAnalyticsDataClient()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[
            Dimension(name="date"),
            Dimension(name="sessionSourceMedium"),
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="conversions"),
        ],
        date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
        dimension_filter=FilterExpression(
            not_expression=FilterExpression(
                or_group=FilterExpressionList(expressions=[
                    FilterExpression(filter=Filter(
                        field_name="country",
                        string_filter=Filter.StringFilter(value=c),
                    )) for c in EXCLUDED_COUNTRIES
                ]),
            ),
        ),
    )
    response = client.run_report(request)

    rows: list[dict] = []
    for row in response.rows:
        rows.append({
            "date": _iso_date(row.dimension_values[0].value),
            "source_medium": row.dimension_values[1].value,
            "sessions": int(row.metric_values[0].value or 0),
            "users": int(row.metric_values[1].value or 0),
            "conversions": float(row.metric_values[2].value or 0.0),
        })
    return rows


def fetch_landing_conversions_last_7_days(property_id: str) -> list[dict]:
    """Liczba eventów `generate_lead` per (date, landingPage, sessionSourceMedium).

    Pozwala atrybuować lead → konkretny landing → źródło. landingPage to pierwsza
    strona w sesji; jeśli ktoś wszedł na /telefonia-voip-dla-firm/ a potem wysłał
    form na /kontakt/, lead jest atrybuowany do /telefonia-voip-dla-firm/.
    """
    client = BetaAnalyticsDataClient()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[
            Dimension(name="date"),
            Dimension(name="landingPage"),
            Dimension(name="sessionSourceMedium"),
        ],
        metrics=[Metric(name="eventCount")],
        date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
        dimension_filter=FilterExpression(
            and_group=FilterExpressionList(expressions=[
                FilterExpression(filter=Filter(
                    field_name="eventName",
                    string_filter=Filter.StringFilter(value="generate_lead"),
                )),
                FilterExpression(not_expression=FilterExpression(
                    or_group=FilterExpressionList(expressions=[
                        FilterExpression(filter=Filter(
                            field_name="country",
                            string_filter=Filter.StringFilter(value=c),
                        )) for c in EXCLUDED_COUNTRIES
                    ]),
                )),
            ]),
        ),
    )
    response = client.run_report(request)
    rows: list[dict] = []
    for row in response.rows:
        rows.append({
            "date": _iso_date(row.dimension_values[0].value),
            "landing": row.dimension_values[1].value or "(unknown)",
            "source_medium": row.dimension_values[2].value,
            "event_count": int(row.metric_values[0].value or 0),
        })
    return rows
