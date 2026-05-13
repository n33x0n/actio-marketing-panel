"""WordPress REST API wrapper for autopublisher."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import mimetypes

import httpx
import markdown as md_lib


def _auth() -> dict:
    user = os.environ["WP_USER"]
    pwd = os.environ["WP_APP_PASSWORD"].replace(" ", "")  # WP app passwords często z spacjami
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _base() -> str:
    return os.environ["WP_BASE_URL"].rstrip("/")


def list_categories() -> list[dict]:
    r = httpx.get(f"{_base()}/wp-json/wp/v2/categories", params={"per_page": 100}, headers=_auth(), timeout=30.0)
    r.raise_for_status()
    return [{"id": c["id"], "name": c["name"], "slug": c["slug"]} for c in r.json()]


def list_tags() -> list[dict]:
    r = httpx.get(f"{_base()}/wp-json/wp/v2/tags", params={"per_page": 100}, headers=_auth(), timeout=30.0)
    r.raise_for_status()
    return [{"id": t["id"], "name": t["name"], "slug": t["slug"]} for t in r.json()]


def find_categories_by_names(names: list[str]) -> list[int]:
    """Mapuje nazwy kategorii (case-insensitive) na ID. Pomija nieznane."""
    if not names:
        return []
    all_cats = list_categories()
    lookup = {c["name"].lower(): c["id"] for c in all_cats}
    return [lookup[n.lower()] for n in names if n.lower() in lookup]


def ensure_tags(names: list[str]) -> list[int]:
    """Mapuje nazwy tagów na ID. Tworzy nowe tagi jeśli nie istnieją."""
    if not names:
        return []
    existing = {t["name"].lower(): t["id"] for t in list_tags()}
    ids = []
    for name in names:
        if name.lower() in existing:
            ids.append(existing[name.lower()])
            continue
        r = httpx.post(
            f"{_base()}/wp-json/wp/v2/tags",
            json={"name": name},
            headers={**_auth(), "Content-Type": "application/json"},
            timeout=30.0,
        )
        if r.status_code in (200, 201):
            ids.append(r.json()["id"])
    return ids


def search_existing_posts(keyword: str) -> list[dict]:
    """Czy keyword jest już pokryty postem? Zwraca listę matchujących."""
    r = httpx.get(
        f"{_base()}/wp-json/wp/v2/posts",
        params={"search": keyword, "per_page": 5, "_fields": "id,title,link,slug"},
        headers=_auth(),
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def upload_media(image_path: str, alt_text: str | None = None) -> dict:
    """Upload obrazu do WP media library. Zwraca {id, url}."""
    p = Path(image_path)
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    with open(p, "rb") as f:
        data = f.read()
    r = httpx.post(
        f"{_base()}/wp-json/wp/v2/media",
        content=data,
        headers={
            **_auth(),
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{p.name}"',
        },
        timeout=60.0,
    )
    r.raise_for_status()
    media = r.json()
    if alt_text:
        httpx.post(
            f"{_base()}/wp-json/wp/v2/media/{media['id']}",
            json={"alt_text": alt_text},
            headers={**_auth(), "Content-Type": "application/json"},
            timeout=30.0,
        )
    return {"id": media["id"], "url": media["source_url"]}


def create_post(
    title: str,
    content_md: str,
    slug: str,
    meta_description: str,
    category_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    featured_media_id: int | None = None,
    status: str = "publish",
) -> dict:
    """Tworzy post w WP. Zwraca {id, url}."""
    content_html = md_lib.markdown(content_md, extensions=["extra", "tables", "fenced_code"])
    payload = {
        "title": title,
        "content": content_html,
        "slug": slug,
        "status": status,
        "excerpt": meta_description,
    }
    if category_ids:
        payload["categories"] = category_ids
    if tag_ids:
        payload["tags"] = tag_ids
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    r = httpx.post(
        f"{_base()}/wp-json/wp/v2/posts",
        json=payload,
        headers={**_auth(), "Content-Type": "application/json"},
        timeout=60.0,
    )
    r.raise_for_status()
    post = r.json()
    return {"id": post["id"], "url": post["link"], "slug": post["slug"]}
