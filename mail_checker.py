"""IMAP fallback dla autopublisher — sprawdza maile na tomasz@actio.pl
i procesuje odpowiedzi: "OK" / "EDIT: opis" / cokolwiek innego."""
from __future__ import annotations

import datetime
import email
import imaplib
import json
import os
import pathlib
import re
import socket
from email.header import decode_header
from email.utils import parseaddr

_mcp = pathlib.Path(__file__).parent / ".mcp.json"
if _mcp.exists():
    try:
        for _k, _v in json.loads(_mcp.read_text())["mcpServers"]["actio-marketing"]["env"].items():
            os.environ.setdefault(_k, _v)
    except Exception:
        pass

import db
import autopublish


SUBJECT_RE = re.compile(r"\[Actio Autopost #(\d+)(?:\s+v\d+)?(?:\s+\(regen\))?\]", re.IGNORECASE)
OK_RE = re.compile(r"^\s*(OK|ok|Ok|oK)\s*$", re.IGNORECASE)
EDIT_RE = re.compile(r"^\s*EDIT:\s*(.+)$", re.IGNORECASE | re.DOTALL)


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key)
    if val:
        return val
    mcp = pathlib.Path(__file__).parent / ".mcp.json"
    if mcp.exists():
        cfg = json.loads(mcp.read_text())
        val = cfg["mcpServers"]["actio-marketing"]["env"].get(key)
        if val:
            return val
    if default is not None:
        return default
    raise RuntimeError(f"Missing env: {key}")


def _csv(key: str) -> set[str]:
    return {e.strip().lower() for e in _env(key, "").split(",") if e.strip()}


def _decode(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = decode_header(raw)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)


def _extract_plain_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        return ""


def _first_meaningful_line(body: str) -> str:
    """Wyciągnij pierwszą non-empty linię przed quote ('On ... wrote:' / '> ...')."""
    lines = body.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        s = line.rstrip()
        if not s:
            if out:
                break
            continue
        if s.startswith(">"):
            break
        if re.match(r"^On .+wrote:\s*$", s):
            break
        if re.match(r"^W dniu .+napisał\(a\):\s*$", s):  # PL Gmail
            break
        if re.match(r"^Dnia .+,.+\s+(napisał|wrote)", s, re.IGNORECASE):
            break
        if "Od:" in s and "Wysłane:" in s:  # OWA quote header
            break
        out.append(s)
    return "\n".join(out).strip()


def check_and_process() -> list[dict]:
    """Główna funkcja — wywoływana przez systemd timer co 30 min."""
    host = _env("AUTOPOST_IMAP_HOST")
    port = int(_env("AUTOPOST_IMAP_PORT", "993"))
    user = _env("AUTOPOST_IMAP_USER")
    pwd = _env("AUTOPOST_IMAP_PASSWORD")

    approvers = _csv("AUTOPOST_APPROVERS")
    if not approvers:
        print("[mail_checker] AUTOPOST_APPROVERS empty — nothing to do")
        return []

    db_path = _env("DB_PATH")
    results: list[dict] = []

    socket.setdefaulttimeout(30)
    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(user, pwd)
        M.select("INBOX")
        # Search unseen messages with Actio Autopost in subject
        typ, data = M.search(None, '(UNSEEN SUBJECT "Actio Autopost")')
        if typ != "OK":
            print(f"[mail_checker] search failed: {typ}")
            return []

        ids = data[0].split()
        print(f"[mail_checker] {len(ids)} unread Actio Autopost messages")

        for msg_id in ids:
            typ, msg_data = M.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data:
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            subject = _decode(msg.get("Subject"))
            from_raw = _decode(msg.get("From"))
            from_email = parseaddr(from_raw)[1].lower()

            m = SUBJECT_RE.search(subject)
            if not m:
                M.store(msg_id, "+FLAGS", "\\Seen")
                continue
            draft_id = int(m.group(1))

            # Anti-spoof: From must be in approvers
            if from_email not in approvers:
                print(f"[mail_checker] draft #{draft_id} skip — from='{from_email}' not in approvers")
                M.store(msg_id, "+FLAGS", "\\Seen")
                continue

            body = _extract_plain_body(msg)
            first = _first_meaningful_line(body)
            print(f"[mail_checker] draft #{draft_id} from={from_email} first_line='{first[:80]}'")

            draft = db.fetch_draft(db_path, draft_id)
            if not draft:
                M.store(msg_id, "+FLAGS", "\\Seen")
                continue
            if draft.get("token_used_at"):
                print(f"[mail_checker] draft #{draft_id} already processed (token_used_at), skip")
                M.store(msg_id, "+FLAGS", "\\Seen")
                continue

            # Decide action
            action = None
            edit_notes = None
            if OK_RE.match(first):
                action = "approve"
            elif EDIT_RE.match(first):
                action = "edit"
                edit_notes = EDIT_RE.match(first).group(1).strip()
            else:
                action = "reject"

            # Mark token used
            db.update_draft(
                db_path, draft_id,
                token_used_at=datetime.datetime.utcnow().isoformat(),
            )

            if action == "approve":
                r = autopublish.publish_draft(draft_id)
                results.append({"draft_id": draft_id, "action": "approve", "result": r})
                print(f"[mail_checker] published #{draft_id}: {r}")
            elif action == "edit":
                r = autopublish.regenerate_with_edits(draft_id, edit_notes)
                db.update_draft(db_path, draft_id, status="regenerating", edit_notes=edit_notes)
                results.append({"draft_id": draft_id, "action": "edit", "result": r})
                print(f"[mail_checker] regenerating #{draft_id}: {r}")
            else:
                db.update_draft(db_path, draft_id, status="rejected", error_log=f"IMAP reject: {first[:100]}")
                results.append({"draft_id": draft_id, "action": "reject", "first_line": first[:100]})
                print(f"[mail_checker] rejected #{draft_id}")

            M.store(msg_id, "+FLAGS", "\\Seen")
    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()

    return results


if __name__ == "__main__":
    results = check_and_process()
    print(json.dumps(results, indent=2, ensure_ascii=False))
