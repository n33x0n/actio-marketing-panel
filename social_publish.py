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


def _upload_unpublished_photo(image_path: str, page_token: str) -> str:
    """Wgraj grafikę jako NIEopublikowane zdjęcie (do attached_media). Zwróć photo_id."""
    page_id = _env("META_PAGE_ID")
    with open(image_path, "rb") as fh:
        r = httpx.post(
            f"{GRAPH}/{page_id}/photos",
            data={"published": "false", "access_token": page_token},
            files={"source": fh},
            timeout=120.0,
        )
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError("photo upload: " + json.dumps(j.get("error", j))[:300])
    return j["id"]


def schedule_fb_photo_post(image_path: str, caption: str, when: str, page_token: str | None = None) -> dict:
    """Zaplanuj post FB ze zdjęciem jako natywny post FEED (widoczny w Business Suite Planner).

    Metoda: upload nieopublikowanego zdjęcia → POST /{page}/feed z attached_media + published=false
    + scheduled_publish_time. NIE używamy /{page}/photos (te nie pokazują się w Plannerze).
    Caption zawiera link UTM jako tekst. Zwraca {ok, post_id, photo_id, error}.
    """
    page_token = page_token or get_page_token()
    page_id = _env("META_PAGE_ID")
    ts = to_unix_waw(when)
    try:
        photo_id = _upload_unpublished_photo(image_path, page_token)
        r = httpx.post(
            f"{GRAPH}/{page_id}/feed",
            data={
                "message": caption,
                "attached_media[0]": json.dumps({"media_fbid": photo_id}),
                "published": "false",
                "scheduled_publish_time": str(ts),
                "access_token": page_token,
            },
            timeout=90.0,
        )
        j = r.json()
        if r.status_code >= 400:
            return {"ok": False, "error": json.dumps(j.get("error", j))[:400]}
        return {"ok": True, "post_id": j.get("id"), "photo_id": photo_id}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def delete_post(post_id: str, page_token: str | None = None) -> tuple[bool, str]:
    """Usuń post/scheduled post (DELETE /{id})."""
    page_token = page_token or get_page_token()
    r = httpx.request("DELETE", f"{GRAPH}/{post_id}", params={"access_token": page_token}, timeout=60.0)
    return r.status_code < 400, r.text[:200]


def _scheduled_photo_index(page_token: str) -> list[dict]:
    """Lista zaplanowanych postów typu photo: {id, when16, msg}."""
    page_id = _env("META_PAGE_ID")
    out = []
    url = f"{GRAPH}/{page_id}/scheduled_posts"
    params = {"fields": "id,scheduled_publish_time,message,attachments{media_type}", "access_token": page_token, "limit": 100}
    for _ in range(10):
        r = httpx.get(url, params=params, timeout=60.0)
        r.raise_for_status()
        j = r.json()
        for p in j.get("data", []):
            att = p.get("attachments", {}).get("data", [{}])
            mt = att[0].get("media_type") if att else None
            if mt != "photo":
                continue
            t = p.get("scheduled_publish_time")
            when16 = datetime.datetime.fromtimestamp(int(t), WAW).strftime("%Y-%m-%d %H:%M") if t else ""
            out.append({"id": p["id"], "when16": when16, "msg": p.get("message", "") or ""})
        nxt = j.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, {}
    return out


def reschedule_fb_as_feed(limit: int | None = None) -> dict:
    """Przeplanuj MOJE zaplanowane posty FB foto (/photos) na widoczne /feed+attached_media.

    Dopasowanie do social_posts po (scheduled_time, prefiks message). NIE rusza obcych/starych
    foto-postów ani link-postów. Uruchamiać NA MIKRUSIE (tam social_posts).
    """
    path = db_path()
    db.init_db(path)
    page_token = get_page_token()
    sched = _scheduled_photo_index(page_token)
    mine = db.fetch_social_posts(path, channel="facebook", status="scheduled")
    stats = {"converted": 0, "skipped_nomatch": 0, "errors": 0}
    used_ids = set()
    for m in mine:
        if limit and stats["converted"] >= limit:
            break
        if "_" in (m.get("fb_post_id") or ""):  # już skonwertowany na /feed (id z podkreśleniem)
            continue
        when16 = m["scheduled_time"][:16]
        match = next((s for s in sched if s["id"] not in used_ids
                      and s["when16"] == when16 and s["msg"][:25] == m["copy"][:25]), None)
        if not match:
            stats["skipped_nomatch"] += 1
            continue
        used_ids.add(match["id"])
        ok_del, _ = delete_post(match["id"], page_token)
        res = schedule_fb_photo_post(m["image_path"], m["copy"], m["scheduled_time"], page_token)
        if res.get("ok"):
            db.update_social_post(path, m["id"], fb_post_id=res["post_id"])
            stats["converted"] += 1
            print(f"  ✓ {when16} przeplanowany (del={ok_del}) → {res['post_id']}")
        else:
            db.update_social_post(path, m["id"], error_log="reschedule: " + str(res.get("error")))
            stats["errors"] += 1
            print(f"  ✗ {when16} BŁĄD: {res.get('error')}")
        time.sleep(2)
    print(f"reschedule_fb_as_feed: {stats}")
    return stats


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


def fix_emdash(limit: int | None = None) -> dict:
    """Zamień pauzę (—) na półpauzę (–): FB zaplanowane = edycja message w miejscu (POST /{id}),
    IG w kolejce = tylko DB (cron użyje poprawionej treści). NIE rusza opublikowanych.
    Uruchamiać NA MIKRUSIE."""
    EM, EN = "—", "–"
    path = db_path()
    db.init_db(path)
    page_token = get_page_token()
    stats = {"fb_edited": 0, "fb_err": 0, "ig_db": 0}
    for r in db.fetch_social_posts(path, channel="facebook", status="scheduled"):
        if EM not in (r["copy"] or ""):
            continue
        if limit and stats["fb_edited"] >= limit:
            break
        new = r["copy"].replace(EM, EN)
        pid = r["fb_post_id"]
        try:
            resp = httpx.post(f"{GRAPH}/{pid}", data={"message": new, "access_token": page_token}, timeout=60.0)
            if resp.status_code < 400:
                db.update_social_post(path, r["id"], copy=new)
                stats["fb_edited"] += 1
                print(f"  ✓ FB {r['scheduled_time']} message zaktualizowany ({pid})")
            else:
                stats["fb_err"] += 1
                print(f"  ✗ FB {r['scheduled_time']} {resp.text[:200]}")
        except Exception as e:
            stats["fb_err"] += 1
            print(f"  ✗ FB {r['scheduled_time']} {type(e).__name__}: {e}")
        time.sleep(1)
    if not limit:
        for r in db.fetch_social_posts(path, channel="instagram", status="queued"):
            if EM in (r["copy"] or ""):
                db.update_social_post(path, r["id"], copy=r["copy"].replace(EM, EN))
                stats["ig_db"] += 1
    print(f"fix_emdash: {stats}")
    return stats


if __name__ == "__main__":
    print(run_ig_due_queue())
