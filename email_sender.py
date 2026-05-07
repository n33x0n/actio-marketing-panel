"""Wysyłka raportów mailem przez Gmail SMTP — dwie grupy odbiorców (CMO/CEO).

CMO dostaje pełny raport z sekcją Rekomendacje. CEO dostaje raport bez tej sekcji.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import markdown as md_lib


def _load_env_from_mcp_json() -> None:
    mcp_path = pathlib.Path(__file__).parent / ".mcp.json"
    if not mcp_path.exists():
        return
    try:
        cfg = json.loads(mcp_path.read_text())
        env = cfg["mcpServers"]["actio-marketing"]["env"]
        for k, v in env.items():
            os.environ.setdefault(k, v)
    except Exception:
        pass


_load_env_from_mcp_json()


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Brak zmiennej środowiskowej: {name}")
    return val


def _parse_recipients(csv: str) -> list[str]:
    return [e.strip() for e in csv.split(",") if e.strip()]


def _strip_recommendations(report_md: str) -> str:
    """Usuń sekcję ## Rekomendacje od jej nagłówka do końca pliku."""
    return re.sub(r"\n+##\s*Rekomendacje.*", "", report_md, flags=re.DOTALL).rstrip() + "\n"


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       color: #222; max-width: 720px; margin: 0 auto; padding: 16px; line-height: 1.5; }
h1 { font-size: 22px; margin-bottom: 4px; }
h2 { font-size: 18px; margin-top: 24px; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }
h3 { font-size: 15px; }
.meta { color: #888; font-size: 13px; margin-bottom: 16px; }
.sync ul { list-style: none; padding-left: 0; font-size: 13px; }
.sync li { padding: 2px 0; }
.alerts { background: #fff5f5; border-left: 4px solid #d32f2f; padding: 8px 12px; margin: 16px 0; }
.alerts h3 { color: #d32f2f; margin: 0 0 8px 0; }
table { border-collapse: collapse; margin: 8px 0; font-size: 13px; }
th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; }
th { background: #f5f5f5; }
code { background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 90%; }
.footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0;
          font-size: 12px; color: #888; }
"""


def _render_html(date_iso: str, report_md: str, sync_status: dict, alerts: list,
                 obsidian_url: str) -> str:
    body_html = md_lib.markdown(report_md, extensions=["tables", "fenced_code"])

    sync_items = "".join(
        f"<li>{'✓' if str(v).startswith('OK') else '✗'} <b>{k}</b>: {v}</li>"
        for k, v in sync_status.items()
    )

    alerts_block = ""
    if alerts:
        items = "".join(f"<li>{a}</li>" for a in alerts)
        alerts_block = (
            f'<div class="alerts"><h3>⚠ Alerty ({len(alerts)})</h3>'
            f'<ul>{items}</ul></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
<h1>Raport Actio Marketing — {date_iso}</h1>
<div class="meta">Wygenerowany automatycznie</div>
<div class="sync"><b>Sync status</b><ul>{sync_items}</ul></div>
{alerts_block}
{body_html}
</body></html>"""


def _render_plain(date_iso: str, report_md: str, sync_status: dict, alerts: list,
                  obsidian_url: str) -> str:
    sync = "\n".join(f"  - {k}: {v}" for k, v in sync_status.items())
    alerts_txt = ""
    if alerts:
        alerts_txt = f"\n⚠ ALERTY ({len(alerts)}):\n" + "\n".join(f"  - {a}" for a in alerts) + "\n"
    return (
        f"Raport Actio Marketing — {date_iso}\n\n"
        f"Sync status:\n{sync}\n"
        f"{alerts_txt}\n"
        f"{report_md}\n"
    )


def _send_via_gmail(to_list: list[str], subject: str, html: str, plain: str) -> None:
    user = _env("GMAIL_USER")
    password = _env("GMAIL_APP_PASSWORD")
    from_name = _env("GMAIL_FROM_NAME", "Marketing Bot")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, user))
    msg["To"] = formataddr((from_name, user))  # widoczny "do siebie" — odbiorcy w BCC
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(user, password)
        s.sendmail(user, [user] + to_list, msg.as_string())


def send_report_email(date_iso: str, report_md: str, sync_status: dict,
                       alerts: list, obsidian_url: str) -> dict:
    """Wysyła raport do dwóch grup. CEO dostaje wersję bez Rekomendacji."""
    cmo = _parse_recipients(os.environ.get("REPORT_RECIPIENTS_CMO", ""))
    ceo = _parse_recipients(os.environ.get("REPORT_RECIPIENTS_CEO", ""))

    alert_marker = f" — ⚠ {len(alerts)} alertów" if alerts else ""
    subject = f"[Actio Marketing] Raport {date_iso}{alert_marker}"

    result = {"cmo": {"sent_to": [], "errors": []},
              "ceo": {"sent_to": [], "errors": []}}

    if cmo:
        try:
            html = _render_html(date_iso, report_md, sync_status, alerts, obsidian_url)
            plain = _render_plain(date_iso, report_md, sync_status, alerts, obsidian_url)
            _send_via_gmail(cmo, subject, html, plain)
            result["cmo"]["sent_to"] = cmo
        except Exception as e:
            result["cmo"]["errors"].append(f"{type(e).__name__}: {e}")

    if ceo:
        try:
            md_ceo = _strip_recommendations(report_md)
            html = _render_html(date_iso, md_ceo, sync_status, alerts, obsidian_url)
            plain = _render_plain(date_iso, md_ceo, sync_status, alerts, obsidian_url)
            _send_via_gmail(ceo, subject, html, plain)
            result["ceo"]["sent_to"] = ceo
        except Exception as e:
            result["ceo"]["errors"].append(f"{type(e).__name__}: {e}")

    return result
