"""Customer Match: upload klientów z CRM do listy ACTIO_CRM_KLIENCI_B2B (9406277210).

Użycie:
    .venv/bin/python3 customer_match_upload.py klienci.csv

CSV: kolumny `email` i/lub `phone` (nagłówek wymagany, reszta kolumn ignorowana).
Normalizacja zgodnie z wymogami Google: email lowercase/trim, telefon E.164 (+48
default), hash SHA-256 przed wysyłką (surowe dane nie opuszczają maszyny).

RODO: wysyłamy wyłącznie hashe; Google działa jako processor (Customer Match
data policy). Lista tylko do obserwacji/biddingu — patrz cmo_context.md.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys

from google.ads.googleads.client import GoogleAdsClient

USER_LIST_ID = 9406277210


def _load_env() -> None:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mcp.json")
    if os.path.exists(path):
        env = json.load(open(path))["mcpServers"]["actio-marketing"]["env"]
        for k, v in env.items():
            if "GOOGLE_ADS" in k:
                os.environ.setdefault(k, v)


def _client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict({
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    })


def norm_email(raw: str) -> str | None:
    e = (raw or "").strip().lower()
    return e if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e) else None


def norm_phone(raw: str) -> str | None:
    """E.164, default +48 (ta sama logika co tel-tracking na actio.pl)."""
    p = re.sub(r"[^\d+]", "", (raw or ""))
    if p.startswith("00"):
        p = "+" + p[2:]
    if p.startswith("+"):
        return p if len(p) > 8 else None
    d = re.sub(r"\D", "", p)
    if len(d) == 9:
        return "+48" + d
    if len(d) == 11 and d.startswith("48"):
        return "+" + d
    return None


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_csv(path: str) -> tuple[list[str], list[str]]:
    emails: set[str] = set()
    phones: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip().lower(): (v or "") for k, v in row.items()}
            if e := norm_email(row.get("email", "")):
                emails.add(e)
            if p := norm_phone(row.get("phone", row.get("telefon", ""))):
                phones.add(p)
    return sorted(emails), sorted(phones)


def upload(csv_path: str) -> None:
    _load_env()
    client = _client()
    cust = os.environ["GOOGLE_ADS_CUSTOMER_ID"]
    emails, phones = read_csv(csv_path)
    print(f"Z CSV: {len(emails)} emaili, {len(phones)} telefonów (po normalizacji+dedup)")
    if not emails and not phones:
        sys.exit("Brak danych do wysyłki — sprawdź nagłówki kolumn (email/phone).")

    job_svc = client.get_service("OfflineUserDataJobService")
    job = client.get_type("OfflineUserDataJob")
    job.type_ = client.enums.OfflineUserDataJobTypeEnum.CUSTOMER_MATCH_USER_LIST
    job.customer_match_user_list_metadata.user_list = (
        f"customers/{cust}/userLists/{USER_LIST_ID}")
    consent = job.customer_match_user_list_metadata.consent
    consent.ad_user_data = client.enums.ConsentStatusEnum.GRANTED
    consent.ad_personalization = client.enums.ConsentStatusEnum.GRANTED

    job_resource = job_svc.create_offline_user_data_job(
        customer_id=cust, job=job).resource_name
    print("Job:", job_resource)

    ops = []
    for e in emails:
        op = client.get_type("OfflineUserDataJobOperation")
        op.create.user_identifiers.add().hashed_email = sha256(e)
        ops.append(op)
    for p in phones:
        op = client.get_type("OfflineUserDataJobOperation")
        op.create.user_identifiers.add().hashed_phone_number = sha256(p)
        ops.append(op)

    for i in range(0, len(ops), 5000):
        job_svc.add_offline_user_data_job_operations(
            resource_name=job_resource, operations=ops[i:i + 5000],
            enable_partial_failure=True)
    job_svc.run_offline_user_data_job(resource_name=job_resource)
    print(f"Wysłano {len(ops)} identyfikatorów, job uruchomiony.")
    print("Status (przetwarzanie do ~kilku h, lista zapełnia się 24-48h):")
    print(f"  GAQL: SELECT offline_user_data_job.status FROM offline_user_data_job "
          f"WHERE offline_user_data_job.resource_name = '{job_resource}'")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    upload(sys.argv[1])
