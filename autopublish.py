"""Autopublisher postów blogowych dla actio.pl.

Flow:
1. GSC top queries 7d (pos 11-30, imp ≥50, nie pokryte)
2. LLM Sonnet 4.6 → title, content_md, meta, categories, tags
3. Nano Banana 2 → featured image
4. DB insert z approval_token
5. SMTP send do recipients TO+CC z 3 linkami webhook
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx
import markdown as md_lib
from slugify import slugify as _slugify_lib


def slugify(text: str) -> str:
    return _slugify_lib(text, max_length=80, lowercase=True)

import db
import gsc
import image_gen
import wp


# === ENV HELPERS ===

def _env(key: str, default: str | None = None) -> str:
    """Read env, fallback to .mcp.json."""
    val = os.environ.get(key)
    if val:
        return val
    mcp = pathlib.Path(__file__).parent / ".mcp.json"
    if mcp.exists():
        try:
            cfg = json.loads(mcp.read_text())
            val = cfg["mcpServers"]["actio-marketing"]["env"].get(key)
            if val:
                return val
        except Exception:
            pass
    if default is not None:
        return default
    raise RuntimeError(f"Missing env: {key}")


def _csv(key: str) -> list[str]:
    raw = _env(key, "")
    return [e.strip() for e in raw.split(",") if e.strip()]


# === GSC PICKER ===

def pick_keyword() -> dict | None:
    """Wybierz keyword z GSC — top 30 queries, pos 11-30, imp ≥50, nie pokryty."""
    db_path = _env("DB_PATH")
    df = db.fetch_gsc_top_queries(db_path, days=14, top=50)
    if df.empty:
        return None

    # Filter: pos 11-30, imp ≥50
    candidates = df[(df["avg_position"] >= 11) & (df["avg_position"] <= 30) & (df["impressions"] >= 50)]

    # Skip queries already covered recently in autopost
    covered = db.fetch_recent_published_keywords(db_path, days=90)

    # Skip queries that already have a dedicated post (tight match: keyword w title lub slug)
    def _kw_already_covered(kw: str) -> bool:
        kw_l = kw.lower()
        kw_slug = slugify(kw)
        try:
            posts = wp.search_existing_posts(kw)
            for p in posts:
                title = (p.get("title", {}).get("rendered") if isinstance(p.get("title"), dict) else p.get("title", "")) or ""
                slug = p.get("slug", "") or ""
                if kw_l in title.lower():
                    return True
                if kw_slug in slug:
                    return True
            return False
        except Exception:
            return False  # WP API failed → assume not covered, try anyway

    for _, row in candidates.iterrows():
        kw = row["query"].strip()
        if not kw or len(kw) < 5:
            continue
        if any(kw.lower() in c.lower() or c.lower() in kw.lower() for c in covered):
            continue
        if _kw_already_covered(kw):
            continue
        return {
            "keyword": kw,
            "position": float(row["avg_position"]),
            "impressions": int(row["impressions"]),
            "clicks": int(row["clicks"]),
        }
    return None


# === LLM ===

def _call_llm(prompt: str) -> str:
    from langfuse.openai import openai
    api_key = _env("OPENROUTER_API_KEY_AUTOPOST")
    model = _env("AUTOPOST_LLM_MODEL", "anthropic/claude-sonnet-4.6")
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://actio-marketing.tomlebioda.com",
            "X-Title": "Actio Marketing Autopost",
        },
        timeout=180.0,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        extra_body={"provider": {"data_collection": "deny"}},
        name="autopublish_draft",
        metadata={"source": "autopublish.py", "use_case": "wp_post_draft"},
    )
    return resp.choices[0].message.content


def _build_prompt(keyword: str, position: float, impressions: int, wp_categories: list[dict], edit_notes: str | None = None) -> str:
    cat_names = ", ".join(f'"{c["name"]}"' for c in wp_categories)
    edit_block = ""
    if edit_notes:
        edit_block = f"\n\n**UWAGI DO POPRAWY (regeneracja)**:\n{edit_notes}\n\nUwzględnij powyższe uwagi w nowej wersji."

    return f"""Jesteś content marketerem Actio (polski operator VoIP B2B, marka SYNTELL S.A., 20+ lat na rynku, klienci m.in. PGE, koleje, Pepco).

Napisz post blogowy pod keyword: "{keyword}"

**Kontekst SEO**:
- GSC pozycja organic: {position:.1f} (chcemy do top 10)
- Wyświetlenia/m: {impressions}

**Wymagania**:
- Tytuł 50-65 znaków, zawiera keyword
- Treść 1000-1500 słów, markdown z H2/H3 sekcjami
- Sekcja "Najczęstsze pytania (FAQ)" na końcu, 5-8 pytań w formacie ### Pytanie? + odpowiedź
- Meta description 140-160 znaków z CTA "Bezpłatna wycena" lub "Sprawdź ofertę"
- W treści MINIMUM 1 wewnętrzny link do relevant /uslugi/* (np. [Wirtualna Centrala](https://actio.pl/uslugi/wirtualna-centrala/))
- Język polski, ton ekspercki B2B, **bez emoji**
- Slug: kebab-case, max 80 znaków, zawiera keyword

**Dostępne kategorie WP** (wybierz 1-2): {cat_names}
**Tagi**: wybierz 5-10 polskich, lowercase, kebab-case (np. "wirtualna-centrala", "voip-dla-firm"){edit_block}

Output: **TYLKO czysty JSON, bez markdown code fence**, taki:
{{
  "title": "...",
  "slug": "...",
  "content_md": "# Tytuł\\n\\n...",
  "meta_description": "...",
  "categories": ["VoIP"],
  "tags": ["tag-1","tag-2"]
}}
"""


def _parse_llm_output(raw: str) -> dict:
    """Wyciągnij JSON z odpowiedzi LLM (czasem opakowany w ```json...```)."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    if not raw.startswith("{"):
        # find first { ... last }
        s = raw.find("{")
        e = raw.rfind("}")
        if s == -1 or e == -1:
            raise ValueError(f"No JSON found in LLM output: {raw[:300]}")
        raw = raw[s:e + 1]
    return json.loads(raw)


# === EMAIL ===

def _render_email_html(draft: dict, draft_id: int, token: str, parent_id: int | None = None) -> str:
    """Render HTML mail z 3 klikalnymi buttonami."""
    base_url = _env("AUTOPOST_WEBHOOK_BASE_URL").rstrip("/")
    approve_url = f"{base_url}/autopost/approve/{draft_id}?token={token}"
    edit_url = f"{base_url}/autopost/edit/{draft_id}?token={token}"
    reject_url = f"{base_url}/autopost/reject/{draft_id}?token={token}"

    content_html = md_lib.markdown(draft["content_md"], extensions=["extra", "tables", "fenced_code"])
    cats = ", ".join(json.loads(draft["categories"]) if isinstance(draft["categories"], str) else draft["categories"])
    tags = ", ".join(json.loads(draft["tags"]) if isinstance(draft["tags"], str) else draft["tags"])

    parent_note = f"<p style='color:#888'><em>Regenerated from draft #{parent_id}</em></p>" if parent_id else ""

    btn_style = "display:inline-block;padding:12px 28px;margin:6px;border-radius:6px;text-decoration:none;font-weight:600;font-family:-apple-system,sans-serif;"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 720px; margin: 0 auto; padding: 16px; color: #222; }}
h1 {{ font-size: 20px; }}
h2 {{ font-size: 18px; margin-top: 24px; }}
.meta {{ background: #f6f8fa; padding: 12px; border-radius: 6px; font-size: 14px; }}
.actions {{ text-align: center; margin: 24px 0; padding: 20px; background: #f0f4f8; border-radius: 8px; }}
.preview {{ border: 1px solid #e1e4e8; padding: 16px; border-radius: 6px; margin-top: 16px; background: #fafbfc; }}
img {{ max-width: 100%; }}
</style></head><body>
<h1>📋 Actio Autopost #{draft_id}</h1>
{parent_note}

<div class="meta">
<strong>Keyword:</strong> {draft['keyword']}<br>
<strong>GSC pozycja:</strong> {draft['gsc_position']:.1f} → cel: top 10<br>
<strong>Wyświetlenia/m:</strong> {draft['gsc_impressions']}<br>
<strong>Tytuł:</strong> {draft['title']}<br>
<strong>Slug:</strong> /{draft['slug']}/<br>
<strong>Meta description:</strong> {draft['meta_description']}<br>
<strong>Kategorie:</strong> {cats}<br>
<strong>Tagi:</strong> {tags}<br>
</div>

<div class="actions">
  <p style="margin:0 0 16px 0;color:#666;font-size:14px"><strong>Status: oczekuje na Twoją decyzję.</strong> Post NIE zostanie opublikowany bez akceptacji.</p>
  <a href="{approve_url}" style="{btn_style}background:#22c55e;color:#fff">✅ AKCEPTUJ I OPUBLIKUJ</a><br>
  <a href="{edit_url}" style="{btn_style}background:#eab308;color:#fff">✏️ POPRAW (z uwagami)</a><br>
  <a href="{reject_url}" style="{btn_style}background:#ef4444;color:#fff">❌ ODRZUĆ</a>
</div>

<p><em>Fallback: jeśli linki nie działają, odpisz na ten mail "OK" (publish), "EDIT: opis zmian" (regeneracja) lub cokolwiek innego (odrzucenie).</em></p>

<h2>📄 Podgląd treści</h2>
<div class="preview">
{content_html}
</div>

<p style="color:#888;font-size:12px;margin-top:32px">
Generated by Actio Marketing Autopost. Po akceptacji post idzie live na actio.pl — wycofać można w WP Admin → Posty (zmiana statusu na Draft).
</p>
</body></html>"""


def _send_draft_email(draft_id: int, draft: dict, token: str, image_path: str | None = None, parent_id: int | None = None) -> str:
    """Wysyła email z draftem przez SMTP Exchange."""
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    host = _env("AUTOPOST_SMTP_HOST")
    port = int(_env("AUTOPOST_SMTP_PORT", "587"))
    user = _env("AUTOPOST_SMTP_USER")
    pwd = _env("AUTOPOST_SMTP_PASSWORD")

    to_list = _csv("AUTOPOST_RECIPIENTS_TO")
    cc_list = _csv("AUTOPOST_RECIPIENTS_CC")

    subject_suffix = f" v2 (regen)" if parent_id else ""
    subject = f"[Actio Autopost #{draft_id}{subject_suffix}] {draft['title']}"

    msg = MIMEMultipart("related")
    msg["From"] = formataddr(("Actio Autopost", user))
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="actio.pl")
    msg["Reply-To"] = user

    body = _render_email_html(draft, draft_id, token, parent_id)
    msg_alt = MIMEMultipart("alternative")
    plain = f"Actio Autopost #{draft_id} — {draft['title']}\n\nKeyword: {draft['keyword']}\n\nOtwórz mail w trybie HTML żeby zobaczyć przyciski."
    msg_alt.attach(MIMEText(plain, "plain", "utf-8"))
    msg_alt.attach(MIMEText(body, "html", "utf-8"))
    msg.attach(msg_alt)

    if image_path and pathlib.Path(image_path).exists():
        with open(image_path, "rb") as f:
            part = MIMEBase("image", "png")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=pathlib.Path(image_path).name)
            msg.attach(part)

    all_recipients = to_list + cc_list
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(user, pwd)
        s.sendmail(user, all_recipients, msg.as_string())

    return msg["Message-ID"]


# === MAIN ENTRY POINTS ===

def generate_draft() -> dict:
    """Główna funkcja — wt+pt 9:00 timer ją odpala."""
    db_path = _env("DB_PATH")
    db.init_db(db_path)

    print("=== Picking keyword from GSC ===")
    pick = pick_keyword()
    if not pick:
        print("Brak kandydatów GSC w zakresie pos 11-30, imp ≥50, nie pokryte.")
        return {"status": "no_keyword"}
    print(f"Picked: {pick['keyword']} (pos {pick['position']:.1f}, imp {pick['impressions']})")

    print("=== Fetching WP categories ===")
    cats = wp.list_categories()

    print("=== Calling LLM ===")
    prompt = _build_prompt(pick["keyword"], pick["position"], pick["impressions"], cats)
    raw = _call_llm(prompt)
    parsed = _parse_llm_output(raw)
    parsed["slug"] = parsed.get("slug") or slugify(parsed["title"])[:80]
    print(f"LLM ok: title='{parsed['title'][:60]}...', content {len(parsed['content_md'])} chars")

    print("=== Generating image (Nano Banana) ===")
    img_dir = pathlib.Path(_env("AUTOPOST_IMAGE_DIR", "autopost_images"))
    img_dir.mkdir(parents=True, exist_ok=True)
    img_prompt = image_gen.build_prompt(pick["keyword"])
    img_path = str(img_dir / f"{parsed['slug']}.png")
    try:
        image_gen.generate_image(img_prompt, img_path)
        print(f"Image: {img_path}")
    except Exception as e:
        print(f"Image gen failed (continuing): {type(e).__name__}: {e}")
        img_path = None

    print("=== Inserting draft to DB ===")
    token = secrets.token_urlsafe(32)
    draft_row = {
        "keyword": pick["keyword"],
        "gsc_position": pick["position"],
        "gsc_impressions": pick["impressions"],
        "title": parsed["title"],
        "slug": parsed["slug"],
        "content_md": parsed["content_md"],
        "meta_description": parsed["meta_description"],
        "categories": json.dumps(parsed.get("categories", []), ensure_ascii=False),
        "tags": json.dumps(parsed.get("tags", []), ensure_ascii=False),
        "image_path": img_path,
        "image_prompt": img_prompt if img_path else None,
        "approval_token": token,
    }
    draft_id = db.insert_draft(db_path, draft_row)
    print(f"Inserted draft #{draft_id}")

    print("=== Sending email ===")
    full_draft = db.fetch_draft(db_path, draft_id)
    try:
        message_id = _send_draft_email(draft_id, full_draft, token, img_path)
        print(f"Email sent: {message_id}")
    except Exception as e:
        print(f"Email failed: {type(e).__name__}: {e}")
        db.update_draft(db_path, draft_id, error_log=f"email_send: {type(e).__name__}: {e}")

    return {"status": "draft_created", "draft_id": draft_id, "keyword": pick["keyword"]}


def regenerate_with_edits(parent_draft_id: int, edit_notes: str) -> dict:
    """Regeneracja draftu z uwagami. Tworzy NOWY draft z parent_draft_id."""
    db_path = _env("DB_PATH")
    parent = db.fetch_draft(db_path, parent_draft_id)
    if not parent:
        return {"status": "parent_not_found"}

    print(f"=== Regenerating draft #{parent_draft_id} with notes ===")
    cats = wp.list_categories()
    prompt = _build_prompt(parent["keyword"], parent["gsc_position"] or 20, parent["gsc_impressions"] or 100, cats, edit_notes=edit_notes)
    raw = _call_llm(prompt)
    parsed = _parse_llm_output(raw)
    parsed["slug"] = parsed.get("slug") or slugify(parsed["title"])[:80]

    # Reuse parent image (nie regeneruj — oszczędność kosztu)
    img_path = parent["image_path"]

    token = secrets.token_urlsafe(32)
    new_row = {
        "keyword": parent["keyword"],
        "gsc_position": parent["gsc_position"],
        "gsc_impressions": parent["gsc_impressions"],
        "title": parsed["title"],
        "slug": parsed["slug"],
        "content_md": parsed["content_md"],
        "meta_description": parsed["meta_description"],
        "categories": json.dumps(parsed.get("categories", []), ensure_ascii=False),
        "tags": json.dumps(parsed.get("tags", []), ensure_ascii=False),
        "image_path": img_path,
        "image_prompt": parent["image_prompt"],
        "approval_token": token,
        "parent_draft_id": parent_draft_id,
        "edit_notes": edit_notes,
    }
    new_draft_id = db.insert_draft(db_path, new_row)

    full_draft = db.fetch_draft(db_path, new_draft_id)
    message_id = _send_draft_email(new_draft_id, full_draft, token, img_path, parent_id=parent_draft_id)
    print(f"Regenerated as #{new_draft_id}, email sent")

    return {"status": "regenerated", "draft_id": new_draft_id, "parent": parent_draft_id}


def publish_draft(draft_id: int) -> dict:
    """Publishuje draft via WP REST. Wywoływane przez webhook (approve) lub mail_checker (OK)."""
    db_path = _env("DB_PATH")
    draft = db.fetch_draft(db_path, draft_id)
    if not draft:
        return {"status": "not_found"}
    if draft["status"] == "published":
        return {"status": "already_published", "post_url": draft["post_url"]}

    try:
        # Map categories
        cat_names = json.loads(draft["categories"]) if draft["categories"] else []
        cat_ids = wp.find_categories_by_names(cat_names)
        if not cat_ids:
            # fallback: default VoIP category (id 10)
            cat_ids = [10]

        # Ensure tags exist
        tag_names = json.loads(draft["tags"]) if draft["tags"] else []
        tag_ids = wp.ensure_tags(tag_names)

        # Upload image
        media_id = None
        if draft["image_path"] and pathlib.Path(draft["image_path"]).exists():
            media = wp.upload_media(draft["image_path"], alt_text=draft["title"])
            media_id = media["id"]

        # Create post
        result = wp.create_post(
            title=draft["title"],
            content_md=draft["content_md"],
            slug=draft["slug"],
            meta_description=draft["meta_description"],
            category_ids=cat_ids,
            tag_ids=tag_ids,
            featured_media_id=media_id,
            status="publish",
        )
        db.update_draft(
            db_path,
            draft_id,
            status="published",
            published_at=__import__("datetime").datetime.utcnow().isoformat(),
            post_url=result["url"],
            post_id=result["id"],
        )
        return {"status": "published", "post_url": result["url"], "post_id": result["id"]}
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        db.update_draft(db_path, draft_id, status="failed", error_log=err)
        return {"status": "error", "error": err}


def process_imap_replies() -> list[dict]:
    """IMAP fallback — sprawdza maile na tomasz@actio.pl i procesuje akceptacje."""
    import mail_checker
    return mail_checker.check_and_process()
