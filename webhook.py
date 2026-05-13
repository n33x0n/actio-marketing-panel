"""FastAPI webhook dla autopublisher — endpoints klikane z mail buttons.

Run: uvicorn webhook:app --host 127.0.0.1 --port 44321
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import secrets

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

import db
import autopublish


app = FastAPI(title="Actio Autopost Webhook")


def _db_path() -> str:
    val = os.environ.get("DB_PATH")
    if val:
        return val
    mcp = pathlib.Path(__file__).parent / ".mcp.json"
    cfg = json.loads(mcp.read_text())
    return cfg["mcpServers"]["actio-marketing"]["env"]["DB_PATH"]


def _verify(draft_id: int, token: str) -> dict:
    draft = db.fetch_draft(_db_path(), draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if not secrets.compare_digest(draft["approval_token"] or "", token):
        raise HTTPException(403, "Invalid token")
    if draft.get("token_used_at"):
        raise HTTPException(409, "Token already used (or different action already taken)")
    return draft


def _page(title: str, body: str, color: str = "#22c55e") -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 640px; margin: 80px auto; padding: 24px; }}
.box {{ background: {color}; color: white; padding: 24px; border-radius: 12px; }}
h1 {{ margin: 0 0 16px 0; }}
a {{ color: white; text-decoration: underline; }}
.body {{ background: #f6f8fa; padding: 24px; border-radius: 8px; margin-top: 16px; }}
textarea {{ width: 100%; min-height: 200px; font-family: inherit; padding: 12px; border: 1px solid #d1d5db; border-radius: 6px; }}
button {{ background: #eab308; color: white; padding: 12px 32px; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; }}
</style></head><body>
<div class="box"><h1>{title}</h1>{body}</div>
</body></html>"""
    return HTMLResponse(html)


@app.get("/autopost/approve/{draft_id}", response_class=HTMLResponse)
def approve(draft_id: int, token: str, request: Request):
    draft = _verify(draft_id, token)

    # Mark token as used FIRST (race condition protection)
    db.update_draft(
        _db_path(), draft_id,
        token_used_at=datetime.datetime.utcnow().isoformat(),
        approved_at=datetime.datetime.utcnow().isoformat(),
    )

    # Publish
    result = autopublish.publish_draft(draft_id)
    if result["status"] == "published":
        return _page(
            "✅ Opublikowane",
            f'<p>Post na actio.pl:</p><p><a href="{result["post_url"]}">{result["post_url"]}</a></p>'
            f'<p>GSC zacznie indeksować w 24-48h. Wycofać można w WP Admin → Posty.</p>',
            color="#22c55e"
        )
    elif result["status"] == "already_published":
        return _page("ℹ️ Już opublikowane", f'<p><a href="{result["post_url"]}">{result["post_url"]}</a></p>', color="#3b82f6")
    else:
        return _page("❌ Błąd publikacji", f'<p>{result.get("error", "Unknown")}</p>', color="#ef4444")


@app.get("/autopost/reject/{draft_id}", response_class=HTMLResponse)
def reject(draft_id: int, token: str):
    draft = _verify(draft_id, token)
    db.update_draft(
        _db_path(), draft_id,
        token_used_at=datetime.datetime.utcnow().isoformat(),
        status="rejected",
    )
    return _page(
        "❌ Odrzucone",
        f'<p>Draft #{draft_id} ("{draft["keyword"]}") oznaczony jako odrzucony.</p>'
        f'<p>Następny draft będzie wygenerowany w kolejnym cyklu (wt/pt 9:00).</p>',
        color="#6b7280"
    )


@app.get("/autopost/edit/{draft_id}", response_class=HTMLResponse)
def edit_form(draft_id: int, token: str):
    draft = _verify(draft_id, token)
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Edytuj draft #{draft_id}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 720px; margin: 40px auto; padding: 24px; }}
h1 {{ margin: 0 0 8px 0; }}
.meta {{ color: #6b7280; font-size: 14px; margin-bottom: 24px; }}
form {{ background: #f6f8fa; padding: 24px; border-radius: 8px; }}
label {{ font-weight: 600; display: block; margin-bottom: 8px; }}
textarea {{ width: 100%; min-height: 180px; font-family: inherit; padding: 12px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; }}
button {{ background: #eab308; color: white; padding: 14px 36px; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; margin-top: 16px; }}
button:hover {{ background: #ca8a04; }}
.preview-link {{ display: inline-block; margin-top: 16px; color: #3b82f6; }}
</style></head><body>
<h1>✏️ Popraw draft #{draft_id}</h1>
<div class="meta">
  <strong>Keyword:</strong> {draft["keyword"]}<br>
  <strong>Tytuł:</strong> {draft["title"]}<br>
</div>
<form method="POST" action="/autopost/edit/{draft_id}?token={token}">
  <label for="edit_notes">Co poprawić? (LLM regeneruje całą treść z uwzględnieniem Twoich uwag)</label>
  <textarea name="edit_notes" placeholder="Np.:
- Dodaj sekcję o integracji z CRM
- Skróć wstęp do 1 akapitu
- Zmień ton na bardziej techniczny
- Dodaj link do /uslugi/3cx-phone-system/"></textarea>
  <button type="submit">📝 Regeneruj draft</button>
</form>
</body></html>""")


@app.post("/autopost/edit/{draft_id}", response_class=HTMLResponse)
def edit_submit(draft_id: int, token: str, edit_notes: str = Form(...)):
    draft = _verify(draft_id, token)

    # Mark token used + parent status
    db.update_draft(
        _db_path(), draft_id,
        token_used_at=datetime.datetime.utcnow().isoformat(),
        status="regenerating",
    )

    # Trigger regenerate (synchronicznie — może chwilę)
    try:
        result = autopublish.regenerate_with_edits(draft_id, edit_notes)
        return _page(
            "✏️ Regeneracja zlecona",
            f'<p>Nowy draft #{result.get("draft_id")} przygotowany.</p>'
            f'<p>Sprawdź skrzynkę email — nowy mail z poprawioną wersją.</p>',
            color="#eab308"
        )
    except Exception as e:
        return _page("❌ Błąd regeneracji", f'<p>{type(e).__name__}: {e}</p>', color="#ef4444")


@app.get("/autopost/health")
def health():
    return {"status": "ok", "service": "autopost-webhook"}
