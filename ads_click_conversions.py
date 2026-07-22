"""Import konwersji offline do Google Ads (gclid) — SENDLY.

Czyta z Cloudflare KV rekordy `adsconv:` (pisane przez sendly-www
functions/api/verify.ts po REALNYM utworzeniu konta), wysyła je do Google Ads
jako ClickConversion i kasuje z KV. Rekord nie zawiera zadnych danych osoby —
tylko identyfikator klikniecia (gclid/gbraid/wbraid), czas i status zgody.

Rekord w KV:
  klucz:   adsconv:<ISO8601>:<rand>
  wartosc: {"gclid"|"gbraid"|"wbraid": ..., "conversion_at": ISO,
            "consent": "granted"|"denied", "language": ..., "form_variant": ...}

Zasady:
- rekord mlodszy niz MIN_AGE_H godzin -> zostaje na nastepny przebieg
  (klik moze jeszcze nie byc w systemie Google; zalecenie Google to >=90 min),
- rekord starszy niz MAX_AGE_DAYS dni -> kasowany bez wysylki (Ads: limit 90 dni),
- sukces wysylki -> klucz kasowany; blad per-rekord (partial failure) -> klucz
  zostaje do retry w kolejnym przebiegu.

Wymagane env (na ra w /opt/sendly-marketing-panel/.env):
  CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_KV_TOKEN (token z uprawnieniem Workers KV
  Storage: Edit — osobny od read-only tokenu analytics), GOOGLE_ADS_*.
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
    if os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
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


def upload(pending: list[tuple[str, dict]]) -> None:
    """pending: [(kv_key, record)] — wysylka jedna paczka, partial failure."""
    from google.ads.googleads.client import GoogleAdsClient

    cfg = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_OAUTH_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_OAUTH_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    }
    client = GoogleAdsClient.load_from_dict(cfg)
    svc = client.get_service("ConversionUploadService")
    action_res = f"customers/{ADS_CUSTOMER_ID}/conversionActions/{ADS_CONV_ACTION_ID}"

    conversions = []
    for _key, rec in pending:
        cc = client.get_type("ClickConversion")
        if rec.get("gclid"):
            cc.gclid = rec["gclid"]
        elif rec.get("gbraid"):
            cc.gbraid = rec["gbraid"]
        elif rec.get("wbraid"):
            cc.wbraid = rec["wbraid"]
        cc.conversion_action = action_res
        at = _parse_at(rec)
        cc.conversion_date_time = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
        consent = (
            client.enums.ConsentStatusEnum.GRANTED
            if rec.get("consent") == "granted"
            else client.enums.ConsentStatusEnum.DENIED
        )
        cc.consent.ad_user_data = consent
        cc.consent.ad_personalization = consent
        conversions.append(cc)

    req = client.get_type("UploadClickConversionsRequest")
    req.customer_id = ADS_CUSTOMER_ID
    req.conversions.extend(conversions)
    req.partial_failure = True
    resp = svc.upload_click_conversions(request=req)

    # Indeksy nieudanych operacji z partial_failure_error.
    failed: dict[int, str] = {}
    pf = resp.partial_failure_error
    if pf and pf.code != 0:
        failure_type = type(client.get_type("GoogleAdsFailure"))
        for detail in pf.details:
            fo = failure_type.deserialize(detail.value)
            for err in fo.errors:
                idx = 0
                for el in err.location.field_path_elements:
                    if el.field_name == "conversions":
                        idx = el.index
                failed[idx] = f"{err.error_code}".strip() or err.message

    ok = 0
    for i, (key, rec) in enumerate(pending):
        if i in failed:
            print(f"  RETRY {key}: {failed[i][:160]}")
            continue
        kv_delete(key)
        ok += 1
        rid = rec.get("gclid") or rec.get("gbraid") or rec.get("wbraid")
        print(f"  OK {key} ({str(rid)[:24]}..., consent={rec.get('consent')})")
    print(f"wyslane: {ok}, do retry: {len(failed)}")


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
        upload(pending)
    return 0


if __name__ == "__main__":
    sys.exit(main())
