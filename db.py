"""SQLite layer dla Marketing Intelligence — init, upsert, fetch."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_conversions (
    date          TEXT    NOT NULL,
    source_medium TEXT    NOT NULL,
    sessions      INTEGER NOT NULL,
    users         INTEGER NOT NULL,
    conversions   REAL    NOT NULL,
    synced_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, source_medium)
);

CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_conversions(date);

CREATE TABLE IF NOT EXISTS gsc_daily (
    date         TEXT    NOT NULL,
    site_url     TEXT    NOT NULL,
    query        TEXT    NOT NULL,
    page         TEXT    NOT NULL,
    impressions  INTEGER NOT NULL,
    clicks       INTEGER NOT NULL,
    ctr          REAL    NOT NULL,
    position     REAL    NOT NULL,
    synced_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, site_url, query, page)
);

CREATE INDEX IF NOT EXISTS idx_gsc_date ON gsc_daily(date);
CREATE INDEX IF NOT EXISTS idx_gsc_query ON gsc_daily(query);
CREATE INDEX IF NOT EXISTS idx_gsc_page ON gsc_daily(page);

CREATE TABLE IF NOT EXISTS ads_campaign_daily (
    date          TEXT    NOT NULL,
    customer_id   TEXT    NOT NULL,
    campaign_id   TEXT    NOT NULL,
    campaign_name TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    clicks        INTEGER NOT NULL,
    impressions   INTEGER NOT NULL,
    cost          REAL    NOT NULL,
    conversions   REAL    NOT NULL,
    conv_value    REAL    NOT NULL,
    synced_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, customer_id, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_ads_camp_date ON ads_campaign_daily(date);
CREATE INDEX IF NOT EXISTS idx_ads_camp_id ON ads_campaign_daily(campaign_id);

CREATE TABLE IF NOT EXISTS ads_keyword_daily (
    date          TEXT    NOT NULL,
    customer_id   TEXT    NOT NULL,
    campaign_id   TEXT    NOT NULL,
    campaign_name TEXT    NOT NULL,
    ad_group_id   TEXT    NOT NULL,
    ad_group_name TEXT    NOT NULL,
    criterion_id  TEXT    NOT NULL,
    keyword       TEXT    NOT NULL,
    match_type    TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    quality_score INTEGER NOT NULL,
    clicks        INTEGER NOT NULL,
    impressions   INTEGER NOT NULL,
    cost          REAL    NOT NULL,
    conversions   REAL    NOT NULL,
    conv_value    REAL    NOT NULL,
    synced_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, customer_id, campaign_id, ad_group_id, criterion_id)
);

CREATE INDEX IF NOT EXISTS idx_ads_kw_date ON ads_keyword_daily(date);
CREATE INDEX IF NOT EXISTS idx_ads_kw_text ON ads_keyword_daily(keyword);

CREATE TABLE IF NOT EXISTS ads_search_term_daily (
    date          TEXT    NOT NULL,
    customer_id   TEXT    NOT NULL,
    campaign_id   TEXT    NOT NULL,
    campaign_name TEXT    NOT NULL,
    ad_group_id   TEXT    NOT NULL,
    ad_group_name TEXT    NOT NULL,
    search_term   TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    clicks        INTEGER NOT NULL,
    impressions   INTEGER NOT NULL,
    cost          REAL    NOT NULL,
    conversions   REAL    NOT NULL,
    conv_value    REAL    NOT NULL,
    synced_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, customer_id, campaign_id, ad_group_id, search_term)
);

CREATE INDEX IF NOT EXISTS idx_ads_st_date ON ads_search_term_daily(date);
CREATE INDEX IF NOT EXISTS idx_ads_st_term ON ads_search_term_daily(search_term);

CREATE TABLE IF NOT EXISTS landing_conversions (
    date          TEXT    NOT NULL,
    landing       TEXT    NOT NULL,
    source_medium TEXT    NOT NULL,
    event_count   INTEGER NOT NULL,
    synced_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, landing, source_medium)
);

CREATE INDEX IF NOT EXISTS idx_landing_conv_date ON landing_conversions(date);
CREATE INDEX IF NOT EXISTS idx_landing_conv_landing ON landing_conversions(landing);

CREATE TABLE IF NOT EXISTS alerts_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at TEXT   NOT NULL DEFAULT (datetime('now')),
    type        TEXT    NOT NULL,
    campaign    TEXT,
    message     TEXT    NOT NULL,
    resolved    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_log_time ON alerts_log(triggered_at);
CREATE INDEX IF NOT EXISTS idx_alerts_log_resolved ON alerts_log(resolved);
"""

# Kolumny dodawane via ALTER TABLE (jeśli istnieje stara wersja DB)
_ADS_CAMPAIGN_LOST_IS_COLS = [
    ("impression_share", "REAL DEFAULT 0"),
    ("budget_lost_is", "REAL DEFAULT 0"),
    ("rank_lost_is", "REAL DEFAULT 0"),
    ("top_is", "REAL DEFAULT 0"),
    ("absolute_top_is", "REAL DEFAULT 0"),
]


@contextmanager
def _connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: str) -> None:
    with _connect(path) as conn:
        conn.executescript(SCHEMA)
        existing = {r[1] for r in conn.execute("PRAGMA table_info(ads_campaign_daily)").fetchall()}
        for col, decl in _ADS_CAMPAIGN_LOST_IS_COLS:
            if col not in existing:
                conn.execute(f"ALTER TABLE ads_campaign_daily ADD COLUMN {col} {decl}")


def upsert_rows(path: str, rows: list[dict]) -> int:
    """INSERT OR UPDATE batch po kluczu (date, source_medium).

    Odświeża metryki dla dni w zakresie syncu, nie usuwa starszych dni poza zakresem.
    """
    if not rows:
        return 0
    sql = """
        INSERT INTO daily_conversions
            (date, source_medium, sessions, users, conversions, synced_at)
        VALUES
            (:date, :source_medium, :sessions, :users, :conversions, datetime('now'))
        ON CONFLICT(date, source_medium) DO UPDATE SET
            sessions    = excluded.sessions,
            users       = excluded.users,
            conversions = excluded.conversions,
            synced_at   = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def fetch_history(
    path: str,
    days: int = 30,
    source_medium: str | None = None,
    offset_days: int = 0,
) -> pd.DataFrame:
    where = [
        "date >= date('now', ?)",
        "date < date('now', ?)",
    ]
    params: list = [
        f"-{int(days + offset_days)} days",
        f"-{int(offset_days)} days" if offset_days > 0 else "+1 day",
    ]
    if source_medium:
        where.append("source_medium = ?")
        params.append(source_medium)
    sql = f"""
        SELECT date, source_medium, sessions, users, conversions, synced_at
        FROM daily_conversions
        WHERE {' AND '.join(where)}
        ORDER BY date ASC, source_medium ASC
    """
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def upsert_gsc_rows(path: str, rows: list[dict]) -> int:
    """INSERT OR UPDATE batch po kluczu (date, site_url, query, page)."""
    if not rows:
        return 0
    sql = """
        INSERT INTO gsc_daily
            (date, site_url, query, page, impressions, clicks, ctr, position, synced_at)
        VALUES
            (:date, :site_url, :query, :page, :impressions, :clicks, :ctr, :position, datetime('now'))
        ON CONFLICT(date, site_url, query, page) DO UPDATE SET
            impressions = excluded.impressions,
            clicks      = excluded.clicks,
            ctr         = excluded.ctr,
            position    = excluded.position,
            synced_at   = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def fetch_gsc_top_queries(
    path: str,
    days: int = 30,
    top: int = 20,
    filter_text: str | None = None,
) -> pd.DataFrame:
    """Top zapytań organic posortowane po liczbie kliknięć (agregat)."""
    where = ["date >= date('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if filter_text:
        where.append("query LIKE ?")
        params.append(f"%{filter_text}%")
    sql = f"""
        SELECT query,
               SUM(impressions) AS impressions,
               SUM(clicks)      AS clicks,
               ROUND(CAST(SUM(clicks) AS REAL) / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr_pct,
               ROUND(AVG(position), 1) AS avg_position
        FROM gsc_daily
        WHERE {' AND '.join(where)}
        GROUP BY query
        ORDER BY clicks DESC, impressions DESC
        LIMIT ?
    """
    params.append(int(top))
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def upsert_ads_campaign_rows(path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO ads_campaign_daily
            (date, customer_id, campaign_id, campaign_name, status,
             clicks, impressions, cost, conversions, conv_value,
             impression_share, budget_lost_is, rank_lost_is, top_is, absolute_top_is,
             synced_at)
        VALUES
            (:date, :customer_id, :campaign_id, :campaign_name, :status,
             :clicks, :impressions, :cost, :conversions, :conv_value,
             :impression_share, :budget_lost_is, :rank_lost_is, :top_is, :absolute_top_is,
             datetime('now'))
        ON CONFLICT(date, customer_id, campaign_id) DO UPDATE SET
            campaign_name    = excluded.campaign_name,
            status           = excluded.status,
            clicks           = excluded.clicks,
            impressions      = excluded.impressions,
            cost             = excluded.cost,
            conversions      = excluded.conversions,
            conv_value       = excluded.conv_value,
            impression_share = excluded.impression_share,
            budget_lost_is   = excluded.budget_lost_is,
            rank_lost_is     = excluded.rank_lost_is,
            top_is           = excluded.top_is,
            absolute_top_is  = excluded.absolute_top_is,
            synced_at        = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def upsert_landing_conversions(path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO landing_conversions
            (date, landing, source_medium, event_count, synced_at)
        VALUES
            (:date, :landing, :source_medium, :event_count, datetime('now'))
        ON CONFLICT(date, landing, source_medium) DO UPDATE SET
            event_count = excluded.event_count,
            synced_at   = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def insert_alert(path: str, type_: str, message: str, campaign: str | None = None) -> int:
    """Zapisuje alert do alerts_log. Zwraca ID alertu."""
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO alerts_log (type, campaign, message) VALUES (?, ?, ?)",
            (type_, campaign, message),
        )
        return cur.lastrowid


def fetch_recent_alerts(path: str, limit: int = 10, only_unresolved: bool = False) -> pd.DataFrame:
    """Ostatnie alerty posortowane DESC po czasie."""
    where = "WHERE resolved = 0" if only_unresolved else ""
    sql = f"""
        SELECT id, triggered_at, type, campaign, message, resolved
        FROM alerts_log
        {where}
        ORDER BY triggered_at DESC
        LIMIT ?
    """
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=[int(limit)])


def resolve_alert(path: str, alert_id: int) -> None:
    with _connect(path) as conn:
        conn.execute("UPDATE alerts_log SET resolved = 1 WHERE id = ?", (alert_id,))


def fetch_landing_conversions(path: str, days: int = 7, top: int = 30) -> pd.DataFrame:
    """Suma generate_lead per (landing, source_medium) w ostatnich N dniach."""
    sql = """
        SELECT landing,
               source_medium,
               SUM(event_count) AS leads
        FROM landing_conversions
        WHERE date >= date('now', ?)
        GROUP BY landing, source_medium
        ORDER BY leads DESC
        LIMIT ?
    """
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=[f"-{int(days)} days", int(top)])


def fetch_ads_campaigns(
    path: str,
    days: int = 7,
    campaign_filter: str | None = None,
    offset_days: int = 0,
) -> pd.DataFrame:
    """Agregat per kampania za N dni z opcjonalnym offsetem (dla week-over-week).

    offset_days=0 → ostatnie 7 dni
    offset_days=7 → poprzednie 7 dni (8-14 dni temu)
    """
    where = [
        "date >= date('now', ?)",
        "date < date('now', ?)",
    ]
    params: list = [
        f"-{int(days + offset_days)} days",
        f"-{int(offset_days)} days" if offset_days > 0 else "+1 day",
    ]
    if campaign_filter:
        where.append("campaign_name LIKE ?")
        params.append(f"%{campaign_filter}%")
    sql = f"""
        SELECT campaign_name,
               status,
               SUM(clicks)      AS clicks,
               SUM(impressions) AS impressions,
               ROUND(SUM(cost), 2)        AS cost_pln,
               ROUND(SUM(conversions), 2) AS conversions,
               ROUND(SUM(conv_value), 2)  AS conv_value,
               ROUND(CAST(SUM(clicks) AS REAL) / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr_pct,
               ROUND(SUM(cost) / NULLIF(SUM(clicks), 0), 2) AS avg_cpc,
               ROUND(SUM(cost) / NULLIF(SUM(conversions), 0), 2) AS cpa,
               ROUND(AVG(impression_share) * 100, 1) AS is_pct,
               ROUND(AVG(budget_lost_is) * 100, 1)   AS lost_budget_pct,
               ROUND(AVG(rank_lost_is) * 100, 1)     AS lost_rank_pct
        FROM ads_campaign_daily
        WHERE {' AND '.join(where)}
        GROUP BY campaign_name, status
        ORDER BY cost_pln DESC
    """
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def upsert_ads_keyword_rows(path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO ads_keyword_daily
            (date, customer_id, campaign_id, campaign_name, ad_group_id, ad_group_name,
             criterion_id, keyword, match_type, status, quality_score,
             clicks, impressions, cost, conversions, conv_value, synced_at)
        VALUES
            (:date, :customer_id, :campaign_id, :campaign_name, :ad_group_id, :ad_group_name,
             :criterion_id, :keyword, :match_type, :status, :quality_score,
             :clicks, :impressions, :cost, :conversions, :conv_value, datetime('now'))
        ON CONFLICT(date, customer_id, campaign_id, ad_group_id, criterion_id) DO UPDATE SET
            campaign_name = excluded.campaign_name,
            ad_group_name = excluded.ad_group_name,
            keyword       = excluded.keyword,
            match_type    = excluded.match_type,
            status        = excluded.status,
            quality_score = excluded.quality_score,
            clicks        = excluded.clicks,
            impressions   = excluded.impressions,
            cost          = excluded.cost,
            conversions   = excluded.conversions,
            conv_value    = excluded.conv_value,
            synced_at     = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def fetch_ads_keywords(
    path: str,
    days: int = 30,
    keyword_filter: str | None = None,
) -> pd.DataFrame:
    where = ["date >= date('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if keyword_filter:
        where.append("keyword LIKE ?")
        params.append(f"%{keyword_filter}%")
    sql = f"""
        SELECT keyword,
               match_type,
               campaign_name,
               ROUND(AVG(quality_score), 1) AS avg_qs,
               SUM(clicks)      AS clicks,
               SUM(impressions) AS impressions,
               ROUND(SUM(cost), 2)        AS cost_pln,
               ROUND(SUM(conversions), 2) AS conversions,
               ROUND(CAST(SUM(clicks) AS REAL) / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr_pct,
               ROUND(SUM(cost) / NULLIF(SUM(clicks), 0), 2) AS avg_cpc,
               ROUND(SUM(cost) / NULLIF(SUM(conversions), 0), 2) AS cpa
        FROM ads_keyword_daily
        WHERE {' AND '.join(where)}
        GROUP BY keyword, match_type, campaign_name
        ORDER BY cost_pln DESC
    """
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def upsert_ads_search_term_rows(path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO ads_search_term_daily
            (date, customer_id, campaign_id, campaign_name, ad_group_id, ad_group_name,
             search_term, status, clicks, impressions, cost, conversions, conv_value, synced_at)
        VALUES
            (:date, :customer_id, :campaign_id, :campaign_name, :ad_group_id, :ad_group_name,
             :search_term, :status, :clicks, :impressions, :cost, :conversions, :conv_value, datetime('now'))
        ON CONFLICT(date, customer_id, campaign_id, ad_group_id, search_term) DO UPDATE SET
            campaign_name = excluded.campaign_name,
            ad_group_name = excluded.ad_group_name,
            status        = excluded.status,
            clicks        = excluded.clicks,
            impressions   = excluded.impressions,
            cost          = excluded.cost,
            conversions   = excluded.conversions,
            conv_value    = excluded.conv_value,
            synced_at     = excluded.synced_at
    """
    with _connect(path) as conn:
        conn.executemany(sql, rows)
    return len(rows)


def fetch_ads_search_terms(
    path: str,
    days: int = 30,
    term_filter: str | None = None,
    top: int = 50,
) -> pd.DataFrame:
    where = ["date >= date('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if term_filter:
        where.append("search_term LIKE ?")
        params.append(f"%{term_filter}%")
    sql = f"""
        SELECT search_term,
               campaign_name,
               SUM(clicks)      AS clicks,
               SUM(impressions) AS impressions,
               ROUND(SUM(cost), 2)        AS cost_pln,
               ROUND(SUM(conversions), 2) AS conversions,
               ROUND(CAST(SUM(clicks) AS REAL) / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr_pct,
               ROUND(SUM(cost) / NULLIF(SUM(clicks), 0), 2) AS avg_cpc
        FROM ads_search_term_daily
        WHERE {' AND '.join(where)}
        GROUP BY search_term, campaign_name
        ORDER BY cost_pln DESC, clicks DESC
        LIMIT ?
    """
    params.append(int(top))
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def fetch_gsc_top_pages(
    path: str,
    days: int = 30,
    top: int = 20,
    filter_text: str | None = None,
) -> pd.DataFrame:
    """Top stron (URL) posortowanych po liczbie kliknięć (agregat)."""
    where = ["date >= date('now', ?)"]
    params: list = [f"-{int(days)} days"]
    if filter_text:
        where.append("page LIKE ?")
        params.append(f"%{filter_text}%")
    sql = f"""
        SELECT page,
               SUM(impressions) AS impressions,
               SUM(clicks)      AS clicks,
               ROUND(CAST(SUM(clicks) AS REAL) / NULLIF(SUM(impressions), 0) * 100, 2) AS ctr_pct,
               ROUND(AVG(position), 1) AS avg_position
        FROM gsc_daily
        WHERE {' AND '.join(where)}
        GROUP BY page
        ORDER BY clicks DESC, impressions DESC
        LIMIT ?
    """
    params.append(int(top))
    with _connect(path) as conn:
        return pd.read_sql_query(sql, conn, params=params)
