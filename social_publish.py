"""Warstwa publikacji social media (Facebook Page + Instagram) przez Meta Graph API.

- Facebook: natywny scheduling (`POST /{page}/photos` z published=false + scheduled_publish_time).
- Instagram: BRAK natywnego schedulingu w Content Publishing API → kolejka w DB
  (`social_posts`) + cron (`run_ig_due_queue`) publikujący o slocie (3-fazowo:
  /media → status poll → /media_publish).

Odtworzone z `__pycache__/schedule_fb.cpython-312.pyc` (utracone źródło) + docs Meta.
Token: META_SYSTEM_USER_TOKEN (system user, no-expiry); page token z /me/accounts.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import time
from zoneinfo import ZoneInfo

import httpx

import db

GRAPH = "https://graph.facebook.com/v18.0"
WAW = ZoneInfo("Europe/Warsaw")
_SOCIAL_IMG_ROOT = pathlib.Path(__file__).parent / "autopost_images" / "social"


# === ENV ===

def _bootstrap_env() -> None:
    """Załaduj env z .mcp.json (DB_PATH, OpenRouter...) + .env (META_*, webhook base)."""
    root = pathlib.Path(__file__).parent
    mcp = root / ".mcp.json"
    if mcp.exists():
        try:
            for k, v in json.loads(mcp.read_text())["mcpServers"]["actio-marketing"]["env"].items():
                os.environ.setdefault(k, v)
        except Exception:
            pass
    env = root / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_bootstrap_env()


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key)
    if val:
        return val
    if default is not None:
        return default
    raise RuntimeError(f"Missing env: {key}")


def db_path() -> str:
    return _env("DB_PATH")


# === TOKENS ===

_page_token_cache: str | None = None


def get_page_token() -> str:
    """Page access token dla META_PAGE_ID (przez system user token + /me/accounts)."""
    global _page_token_cache
    if _page_token_cache:
        return _page_token_cache
    tok = _env("META_SYSTEM_USER_TOKEN")
    page_id = _env("META_PAGE_ID")
    r = httpx.get(
        f"{GRAPH}/me/accounts",
        params={"access_token": tok, "fields": "access_token,id", "limit": 50},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    for acc in data:
        if str(acc.get("id")) == str(page_id):
            _page_token_cache = acc["access_token"]
            return _page_token_cache
    if data:  # fallback: pierwsza dostępna strona
        _page_token_cache = data[0]["access_token"]
        return _page_token_cache
    raise RuntimeError("Brak dostępnych stron FB dla tego tokenu (sprawdź scope pages_show_list)")


# === FACEBOOK ===

def to_unix_waw(when: str | datetime.datetime) -> int:
    """ISO 'YYYY-MM-DD HH:MM' (Europe/Warsaw) → UNIX timestamp."""
    if isinstance(when, str):
        dt = datetime.datetime.strptime(when.strip()[:16], "%Y-%m-%d %H:%M")
    else:
        dt = when
    return int(dt.replace(tzinfo=WAW).timestamp())


def schedule_fb_photo_post(image_path: str, caption: str, when: str, page_token: str | None = None) -> dict:
    """Zaplanuj post FB z grafiką (photo + caption + scheduled_publish_time).

    Zwraca {ok, post_id, error}. Caption zawiera link UTM jako tekst (post /photos
    nie ma klikalnej karty OG, link leci w treści).
    """
    page_token = page_token or get_page_token()
    page_id = _env("META_PAGE_ID")
    ts = to_unix_waw(when)
    try:
        with open(image_path, "rb") as fh:
            r = httpx.post(
                f"{GRAPH}/{page_id}/photos",
                data={
                    "caption": caption,
                    "published": "false",
                    "scheduled_publish_time": str(ts),
                    "access_token": page_token,
                },
                files={"source": fh},
                timeout=120.0,
            )
        j = r.json()
        if r.status_code >= 400:
            return {"ok": False, "error": json.dumps(j.get("error", j))[:400]}
        return {"ok": True, "post_id": j.get("id") or j.get("post_id")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def list_fb_scheduled(page_token: str | None = None) -> list[dict]:
    """Lista zaplanowanych (unpublished) postów FB: {id, scheduled_publish_time, message}."""
    page_token = page_token or get_page_token()
    page_id = _env("META_PAGE_ID")
    out: list[dict] = []
    url = f"{GRAPH}/{page_id}/scheduled_posts"
    params = {"fields": "id,scheduled_publish_time,message", "access_token": page_token, "limit": 100}
    for _ in range(10):  # paginacja, max 10 stron
        r = httpx.get(url, params=params, timeout=60.0)
        r.raise_for_status()
        j = r.json()
        out.extend(j.get("data", []))
        nxt = j.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, {}
    return out


def fb_scheduled_dates(page_token: str | None = None) -> set[str]:
    """Zbiór dat 'YYYY-MM-DD' które mają już zaplanowany post FB (do wykrywania zajętych slotów)."""
    dates = set()
    for p in list_fb_scheduled(page_token):
        t = p.get("scheduled_publish_time")
        if t:
            dt = datetime.datetime.fromtimestamp(int(t), WAW)
            dates.add(dt.strftime("%Y-%m-%d"))
    return dates


# === INSTAGRAM (3-fazowa publikacja, brak natywnego schedulingu) ===

def ig_public_url(image_path: str) -> str:
    """Lokalna ścieżka grafiki IG → publiczny URL (przez webhook /autopost/img)."""
    base = _env("AUTOPOST_WEBHOOK_BASE_URL").rstrip("/")
    p = pathlib.Path(image_path).resolve()
    rel = p.relative_to(_SOCIAL_IMG_ROOT.resolve())
    return f"{base}/autopost/img/{rel.as_posix()}"


def ig_create_container(image_url: str, caption: str, page_token: str | None = None) -> dict:
    page_token = page_token or get_page_token()
    ig_id = _env("META_IG_BUSINESS_ID")
    r = httpx.post(
        f"{GRAPH}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": page_token},
        timeout=90.0,
    )
    j = r.json()
    if r.status_code >= 400:
        return {"ok": False, "error": json.dumps(j.get("error", j))[:400]}
    return {"ok": True, "creation_id": j.get("id")}


def ig_wait_finished(creation_id: str, page_token: str | None = None, tries: int = 12, delay: float = 5.0) -> bool:
    page_token = page_token or get_page_token()
    for _ in range(tries):
        r = httpx.get(
            f"{GRAPH}/{creation_id}",
            params={"fields": "status_code", "access_token": page_token},
            timeout=60.0,
        )
        if r.status_code < 400 and r.json().get("status_code") == "FINISHED":
            return True
        time.sleep(delay)
    return False


def ig_publish(creation_id: str, page_token: str | None = None) -> dict:
    page_token = page_token or get_page_token()
    ig_id = _env("META_IG_BUSINESS_ID")
    r = httpx.post(
        f"{GRAPH}/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": page_token},
        timeout=90.0,
    )
    j = r.json()
    if r.status_code >= 400:
        return {"ok": False, "error": json.dumps(j.get("error", j))[:400]}
    return {"ok": True, "media_id": j.get("id")}


def run_ig_due_queue() -> dict:
    """Cron (Mikrus, co 15 min): opublikuj zaległe posty IG z kolejki social_posts."""
    path = db_path()
    db.init_db(path)
    page_token = get_page_token()
    now_iso = datetime.datetime.now(WAW).strftime("%Y-%m-%d %H:%M")
    due = db.fetch_due_ig_posts(path, now_iso)
    results = {"due": len(due), "published": 0, "failed": 0}
    for post in due:
        pid = post["id"]
        # lock optimistyczny: oznacz 'publishing' żeby kolejny tick nie dublował
        db.update_social_post(path, pid, status="publishing")
        try:
            img_url = ig_public_url(post["image_path"])
            cont = ig_create_container(img_url, post["copy"], page_token)
            if not cont.get("ok"):
                db.update_social_post(path, pid, status="failed", error_log=f"container: {cont.get('error')}")
                results["failed"] += 1
                continue
            cid = cont["creation_id"]
            db.update_social_post(path, pid, ig_creation_id=cid)
            if not ig_wait_finished(cid, page_token):
                db.update_social_post(path, pid, status="failed", error_log="container not FINISHED")
                results["failed"] += 1
                continue
            pub = ig_publish(cid, page_token)
            if not pub.get("ok"):
                db.update_social_post(path, pid, status="failed", error_log=f"publish: {pub.get('error')}")
                results["failed"] += 1
                continue
            db.update_social_post(
                path, pid, status="published", ig_media_id=pub["media_id"],
                published_at=datetime.datetime.utcnow().isoformat(),
            )
            results["published"] += 1
            time.sleep(2)
        except Exception as e:
            db.update_social_post(path, pid, status="failed", error_log=f"{type(e).__name__}: {e}")
            results["failed"] += 1
    print(f"[ig_queue] {now_iso} :: {results}")
    return results


if __name__ == "__main__":
    print(run_ig_due_queue())
