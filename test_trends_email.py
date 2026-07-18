"""Test sekcji 'Trendy na dzisiaj' — buduje sekcję i wysyła TESTOWY mail TYLKO do Toma.

Uruchamiać na VPS ra (ma OPENROUTER_API_KEY + GMAIL_*). Adresat = pierwszy z
REPORT_RECIPIENTS_CMO (Tom); Hubert NIE dostaje. Nie rusza normalnego pipeline'u.
"""
import os

import markdown as md_lib

import email_sender
import panel_positive_report as ppr
import trends

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
