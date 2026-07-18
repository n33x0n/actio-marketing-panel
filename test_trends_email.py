"""Test sekcji 'Trendy na dzisiaj' — buduje sekcję i wysyła TESTOWY mail TYLKO do Toma.

Uruchamiać na VPS ra: `.venv/bin/python test_trends_email.py`.
Sam ładuje .env (odporny na wartości ze spacjami) i wymusza BRAND=sendly.
Adresat = pierwszy z REPORT_RECIPIENTS_CMO (Tom); Hubert NIE dostaje.
"""
import os
import pathlib


def _load_env() -> None:
    p = pathlib.Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
os.environ.setdefault("BRAND", "sendly")  # test jest pod SENDLY

import markdown as md_lib  # noqa: E402

import email_sender  # noqa: E402
import panel_positive_report as ppr  # noqa: E402
import trends  # noqa: E402

section = trends.build_trends_section()
if not section.strip():
    section = "## 📈 Trendy na dzisiaj\n\n_(dziś pusto albo błąd pobierania — sprawdź logi)_\n"

body_md = (
    '# SENDLY — TEST sekcji „Trendy na dzisiaj"\n\n'
    "To testowy mail (tylko do Ciebie). Poniżej dokładnie ta sekcja, która wejdzie na "
    "koniec codziennego raportu SENDLY (do Ciebie i do Huberta).\n\n---\n\n" + section
)

inner = md_lib.markdown(body_md, extensions=["extra", "tables", "fenced_code"])
html = ppr._wrap_html(inner)

to = (os.environ.get("REPORT_RECIPIENTS_CMO") or "tlebioda@gmail.com").split(",")[0].strip()
email_sender._send_via_gmail([to], "[SENDLY] TEST — Trendy na dzisiaj", html, body_md)
print("Wyslano testowy mail do:", to)
