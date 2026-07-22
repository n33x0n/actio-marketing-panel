"""Import konwersji offline do Google Ads (gclid) — SENDLY, przez Data Manager API.

Czyta z Cloudflare KV rekordy `adsconv:` (pisane przez sendly-www
functions/api/verify.ts po REALNYM utworzeniu konta) i wysyla je do Google Ads
przez Data Manager API (events:ingest). Rekord nie zawiera zadnych danych osoby —
tylko identyfikator klikniecia (gclid/gbraid/wbraid), czas i status zgody.

UWAGA: stary ConversionUploadService.UploadClickConversions zwraca dla nowych
integracji CUSTOMER_NOT_ALLOWLISTED_FOR_THIS_FEATURE — Google wymaga Data Manager
API (datamanager.googleapis.com), scope OAuth `auth/datamanager`, bez developer
tokenu. Ingestia jest ASYNCHRONICZNA: 200 = przyjete (requestId), bledy per-event
nie wracaja synchronicznie; dedup po transactionId czyni retry bezpiecznym.

Rekord w KV:
  klucz:   adsconv:<ISO8601>:<rand>
  wartosc: {"gclid"|"gbraid"|"wbraid": ..., "conversion_at": ISO,
            "consent": "granted"|"denied", "language": ..., "form_variant": ...}

Zasady:
- rekord mlodszy niz MIN_AGE_H godzin -> zostaje na nastepny przebieg
  (klik moze jeszcze nie byc w systemie Google; zalecenie Google to >=90 min),
- rekord starszy niz MAX_AGE_DAYS dni -> kasowany bez wysylki (Ads: limit 90 dni),
- przyjecie paczki (200) -> klucz przenoszony na `adsconv-sent:` (audyt, TTL 60 dni),
  oryginal kasowany; blad HTTP -> klucze zostaja do retry.

Wymagane env (na ra w /opt/sendly-marketing-panel/.env):
  CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_KV_TOKEN (Workers KV Storage: Edit),
  GOOGLE_ADS_OAUTH_CLIENT_ID/SECRET, DATAMANAGER_REFRESH_TOKEN (scope datamanager),
  GOOGLE_ADS_LOGIN_CUSTOMER_ID (MCC jako loginAccount).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

KV_NAMESPACE_ID = os.environ.get("DIAG_KV_NAMESPACE_ID", "70d3b7e728034718843bf5ce3be6ecd9")
ADS_CUSTOMER_ID = os.environ.get("ADS_CONV_CUSTOMER_ID", "2556473852")
ADS_CONV_ACTION_ID = os.environ.get("ADS_CONV_ACTION_ID", "7693745003")
MIN_AGE_H = 6
MAX_AGE_DAYS = 88
PREFIX = "adsconv:"


def _load_env_fallback() -> None:
    """Przy recznym uruchomieniu (bez systemd EnvironmentFile) doczytaj .env."""
    if os.environ.get("DATAMANAGER_REFRESH_TOKEN"):
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _kv_base() -> str:
    acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    return f"https://api.cloudflare.com/client/v4/accounts/{acct}/storage/kv/namespaces/{KV_NAMESPACE_ID}"


def _kv_headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['CLOUDFLARE_KV_TOKEN']}"}


def kv_list_pending() -> list[str]:
    r = requests.get(
        f"{_kv_base()}/keys",
        params={"prefix": PREFIX, "limit": 1000},
        headers=_kv_headers(),
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"KV list: {data.get('errors')}")
    return [k["name"] for k in data["result"]]


def kv_get(key: str) -> dict | None:
    r = requests.get(
        f"{_kv_base()}/values/{urllib.parse.quote(key, safe='')}",
        headers=_kv_headers(),
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return None


def kv_delete(key: str) -> None:
    r = requests.delete(
        f"{_kv_base()}/values/{urllib.parse.quote(key, safe='')}",
        headers=_kv_headers(),
        timeout=30,
    )
    r.raise_for_status()


def _parse_at(rec: dict) -> datetime | None:
    raw = rec.get("conversion_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def kv_put(key: str, value: str, ttl_s: int | None = None) -> None:
    params = {"expiration_ttl": ttl_s} if ttl_s else {}
    r = requests.put(
        f"{_kv_base()}/values/{urllib.parse.quote(key, safe='')}",
        params=params,
        headers=_kv_headers(),
        data=value.encode("utf-8"),
        timeout=30,
    )
    r.raise_for_status()


def _dm_access_token() -> str:
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["DATAMANAGER_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def upload(pending: list[tuple[str, dict]], validate_only: bool = False) -> bool:
    """pending: [(kv_key, record)] — jedna paczka do Data Manager events:ingest.

    Zwraca True gdy paczka przyjeta (200). Ingestia asynchroniczna — bledy
    per-event nie wracaja tutaj; transactionId (suffix klucza KV) daje dedup.
    """
    login_cid = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    dest = {
        "reference": "conv",
        "operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": ADS_CUSTOMER_ID},
        "productDestinationId": ADS_CONV_ACTION_ID,
    }
    if login_cid and login_cid != ADS_CUSTOMER_ID:
        dest["loginAccount"] = {"accountType": "GOOGLE_ADS", "accountId": login_cid}

    events = []
    for key, rec in pending:
        at = _parse_at(rec)
        consent = "CONSENT_GRANTED" if rec.get("consent") == "granted" else "CONSENT_DENIED"
        ev: dict = {
            "destinationReferences": ["conv"],
            # suffix klucza KV = stabilny id -> retry nie dubluje konwersji
            "transactionId": key.rsplit(":", 1)[-1],
            "eventTimestamp": at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "consent": {"adUserData": consent, "adPersonalization": consent},
            "adIdentifiers": {},
        }
        for f in ("gclid", "gbraid", "wbraid"):
            if rec.get(f):
                ev["adIdentifiers"][f] = rec[f]
                break
        events.append(ev)

    body = {"destinations": [dest], "events": events}
    if validate_only:
        body["validateOnly"] = True
    r = requests.post(
        "https://datamanager.googleapis.com/v1/events:ingest",
        headers={
            "Authorization": f"Bearer {_dm_access_token()}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60,
    )
    if r.status_code != 200:
        print(f"  BLAD ingest HTTP {r.status_code}: {r.text[:400]} — rekordy zostaja do retry")
        return False

    rid = r.json().get("requestId", "?")
    print(f"  paczka przyjeta (requestId={rid}, events={len(events)}, validateOnly={validate_only})")
    if validate_only:
        return True
    for key, rec in pending:
        # audyt: przenies na adsconv-sent: (TTL 60 dni), skasuj oryginal
        sent = dict(rec)
        sent["dm_request_id"] = rid
        sent["sent_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        kv_put(f"adsconv-sent:{key[len(PREFIX):]}", json.dumps(sent), ttl_s=60 * 24 * 3600)
        kv_delete(key)
        cid = rec.get("gclid") or rec.get("gbraid") or rec.get("wbraid")
        print(f"  OK {key} ({str(cid)[:24]}..., consent={rec.get('consent')})")
    return True


def main() -> int:
    _load_env_fallback()
    now = datetime.now(timezone.utc)
    keys = kv_list_pending()
    print(f"[{now.isoformat(timespec='seconds')}] rekordow adsconv w KV: {len(keys)}")
    if not keys:
        return 0

    pending: list[tuple[str, dict]] = []
    for key in keys:
        rec = kv_get(key)
        if rec is None:
            continue
        at = _parse_at(rec)
        if at is None or not (rec.get("gclid") or rec.get("gbraid") or rec.get("wbraid")):
            print(f"  DROP {key}: rekord niekompletny")
            kv_delete(key)
            continue
        age = now - at
        if age < timedelta(hours=MIN_AGE_H):
            print(f"  SKIP {key}: mlodszy niz {MIN_AGE_H}h — nastepny przebieg")
            continue
        if age > timedelta(days=MAX_AGE_DAYS):
            print(f"  DROP {key}: starszy niz {MAX_AGE_DAYS} dni (limit Ads)")
            kv_delete(key)
            continue
        pending.append((key, rec))

    if pending:
        upload(pending, validate_only="--validate" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
