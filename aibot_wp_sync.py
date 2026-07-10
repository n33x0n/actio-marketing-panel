"""Ciągła synchronizacja botów AI: WP (wp_actio_ai_bot_hits) -> SQLite ai_bot_hits (Mikrus).

Przyrostowo po id (kolumna wp_id w SQLite, unikalna) – idempotentne, można wołać dowolnie często.
Uruchamiane z systemd timera co 10 min do cutoveru; po cutoverze timer wyłączyć
(zapis przejmuje w całości ingest CF /autopost/aibot, ten sam schemat, wp_id=NULL).

Env: ACTIO_AIBOT_TOKEN (fallback: .mcp.json), DB_PATH (fallback: social_publish.db_path()).
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys

import httpx

RAW_URL = "https://actio.pl/wp-json/actio/v1/ai-bots-raw"
PAGE_LIMIT = 1000


def _env(key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    mcp = pathlib.Path(__file__).parent / ".mcp.json"
    if mcp.exists():
        try:
            cfg = json.loads(mcp.read_text())
            for srv in cfg.get("mcpServers", {}).values():
                v = srv.get("env", {}).get(key)
                if v:
                    return v
        except Exception:
            pass
    return None


def _db_path() -> str:
    p = _env("DB_PATH")
    if p:
        return p
    import social_publish as sp  # fallback: ta sama baza co reszta stacku
    return sp.db_path()


def ensure_schema(conn: sqlite3.Connection) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ai_bot_hits)").fetchall()]
    if "wp_id" not in cols:
        conn.execute("ALTER TABLE ai_bot_hits ADD COLUMN wp_id INTEGER")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_aibot_wpid ON ai_bot_hits(wp_id)")
    conn.commit()


def sync() -> dict:
    token = _env("ACTIO_AIBOT_TOKEN")
    if not token:
        print("brak ACTIO_AIBOT_TOKEN", file=sys.stderr)
        return {"error": "no_token"}

    conn = sqlite3.connect(_db_path())
    ensure_schema(conn)
    after = conn.execute("SELECT COALESCE(MAX(wp_id), 0) FROM ai_bot_hits").fetchone()[0]
    start_after = after
    inserted = 0

    while True:
        r = httpx.get(RAW_URL, params={"token": token, "after_id": after, "limit": PAGE_LIMIT}, timeout=30)
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", [])
        if not rows:
            break
        conn.executemany(
            "INSERT OR IGNORE INTO ai_bot_hits (hit_time, bot, purpose, path, ua, wp_id) VALUES (?,?,?,?,?,?)",
            [(x["hit_time"], x["bot"], x["purpose"], x.get("path"), x.get("ua"), int(x["id"])) for x in rows],
        )
        conn.commit()
        inserted += len(rows)
        after = int(rows[-1]["id"])
        if len(rows) < PAGE_LIMIT:
            break

    total = conn.execute("SELECT COUNT(*) FROM ai_bot_hits").fetchone()[0]
    wp_rows = conn.execute("SELECT COUNT(*) FROM ai_bot_hits WHERE wp_id IS NOT NULL").fetchone()[0]
    conn.close()
    out = {"start_after": start_after, "fetched": inserted, "last_wp_id": after, "total_sqlite": total, "wp_rows": wp_rows}
    print(f"aibot_wp_sync: {out}")
    return out


if __name__ == "__main__":
    sync()
