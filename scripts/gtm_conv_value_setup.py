"""Wdrożenie dynamic conv_value w GTM przez API.

Tworzy:
- Lookup Table variable 'Lead Value by URL' (Page Path -> value PLN)
- Constant variable 'Currency PLN'
- Update tagu 4 (form submission) i 6 (phone click) - dodaje value + currency
- Tworzy nową wersję (NIE publikuje - Tom klika sam)
"""
from __future__ import annotations

import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ACCOUNT_ID = "6311155294"
CONTAINER_ID = "228932433"
WORKSPACE_ID = "6"
WS = f"accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}/workspaces/{WORKSPACE_ID}"
TAG_FORM_ID = "4"
TAG_PHONE_ID = "6"

URL_TO_VALUE = [
    ("/uslugi/sip-trunk/", "2400"),
    ("/uslugi/3cx-phone-system/", "3000"),
    ("/uslugi/twoj-3cx-moze-wiecej-odkryj-sip-trunk-z-obsluga-sms/", "3000"),
    ("/uslugi/sms-api/", "3600"),
    ("/uslugi/blyskawiczna-komunikacja-sms-tam-gdzie-sa-twoi-klienci/", "3600"),
    ("/uslugi/efektywna-komunikacja-sms-dla-twojej-firmy/", "3600"),
    ("/uslugi/sms-przez-voip/", "3600"),
    ("/uslugi/wirtualna-centrala/", "3300"),
    ("/uslugi/actio-mobile/", "360"),
    ("/uslugi/wirtualny-numer-komorkowy-voip/", "360"),
    ("/uslugi/rozwiazania-sztucznej-inteligencji-ai-w-komunikacji/", "3000"),
    ("/uslugi/ankiety-telefoniczne/", "3000"),
    ("/uslugi/nowoczesna-komunikacja-glosowa-z-voip/", "1200"),
    ("/uslugi/nowoczesna-komunikacja-video-spotkania-twarza-w-twarz-bez-barier/", "1200"),
    ("/uslugi/wideokonferencja/", "1200"),
    ("/uslugi/telekonferencja/", "1200"),
    ("/uslugi/wirtualny-fax/", "600"),
    ("/uslugi/poczta-glosowa/", "600"),
    ("/uslugi/przekierowanie-polaczen/", "600"),
    ("/uslugi/zarzadzanie-nieodebranymi-polaczeniami/", "600"),
    ("/uslugi/wsparcie-sprzedazy/", "600"),
    ("/uslugi/zachowaj-swoj-numer-i-przejdz-do-actio-szybko-bezplatnie-i-bez-przerw-w-dzialaniu/", "600"),
]
DEFAULT_VALUE = "900"


def gtm_client():
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=[
            "https://www.googleapis.com/auth/tagmanager.edit.containers",
            "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
            "https://www.googleapis.com/auth/tagmanager.publish",
        ],
    )
    return build("tagmanager", "v2", credentials=creds)


def build_lookup_table_body() -> dict:
    return {
        "name": "Lead Value by URL",
        "type": "smm",
        "parameter": [
            {"type": "template", "key": "input", "value": "{{Page Path}}"},
            {"type": "boolean", "key": "setDefaultValue", "value": "true"},
            {"type": "template", "key": "defaultValue", "value": DEFAULT_VALUE},
            {
                "type": "list",
                "key": "map",
                "list": [
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "key", "value": url},
                            {"type": "template", "key": "value", "value": val},
                        ],
                    }
                    for url, val in URL_TO_VALUE
                ],
            },
        ],
    }


def build_constant_body() -> dict:
    return {
        "name": "Currency PLN",
        "type": "c",
        "parameter": [
            {"type": "template", "key": "value", "value": "PLN"},
        ],
    }


def add_value_currency_to_tag(tag: dict) -> dict:
    """Dodaje 2 wpisy (value, currency) do eventSettingsTable tagu."""
    new_tag = json.loads(json.dumps(tag))
    for p in new_tag["parameter"]:
        if p.get("key") == "eventSettingsTable" and p.get("type") == "list":
            existing_params = set()
            for entry in p["list"]:
                for kv in entry.get("map", []):
                    if kv.get("key") == "parameter":
                        existing_params.add(kv.get("value"))
            additions = []
            if "value" not in existing_params:
                additions.append(
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "value"},
                            {"type": "template", "key": "parameterValue", "value": "{{Lead Value by URL}}"},
                        ],
                    }
                )
            if "currency" not in existing_params:
                additions.append(
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "currency"},
                            {"type": "template", "key": "parameterValue", "value": "{{Currency PLN}}"},
                        ],
                    }
                )
            p["list"].extend(additions)
            return new_tag
    raise RuntimeError("eventSettingsTable not found in tag")


def find_variable_by_name(gtm, name: str):
    res = gtm.accounts().containers().workspaces().variables().list(parent=WS).execute()
    for v in res.get("variable", []):
        if v["name"] == name:
            return v
    return None


def main():
    with open(".mcp.json") as f:
        env = json.load(f)["mcpServers"]["actio-marketing"]["env"]
    os.environ.update(env)

    gtm = gtm_client()

    # 1. Lookup Table
    existing = find_variable_by_name(gtm, "Lead Value by URL")
    body = build_lookup_table_body()
    if existing:
        body["variableId"] = existing["variableId"]
        body["path"] = existing["path"]
        body["fingerprint"] = existing["fingerprint"]
        r = gtm.accounts().containers().workspaces().variables().update(
            path=existing["path"], body=body
        ).execute()
        print(f"[UPDATE] Lookup Table 'Lead Value by URL' -> {r['variableId']}")
    else:
        r = gtm.accounts().containers().workspaces().variables().create(
            parent=WS, body=body
        ).execute()
        print(f"[CREATE] Lookup Table 'Lead Value by URL' -> {r['variableId']}")

    # 2. Constant
    existing = find_variable_by_name(gtm, "Currency PLN")
    body = build_constant_body()
    if existing:
        body["variableId"] = existing["variableId"]
        body["path"] = existing["path"]
        body["fingerprint"] = existing["fingerprint"]
        r = gtm.accounts().containers().workspaces().variables().update(
            path=existing["path"], body=body
        ).execute()
        print(f"[UPDATE] Constant 'Currency PLN' -> {r['variableId']}")
    else:
        r = gtm.accounts().containers().workspaces().variables().create(
            parent=WS, body=body
        ).execute()
        print(f"[CREATE] Constant 'Currency PLN' -> {r['variableId']}")

    # 3. Update tag form submission
    tag = gtm.accounts().containers().workspaces().tags().get(
        path=f"{WS}/tags/{TAG_FORM_ID}"
    ).execute()
    new_tag = add_value_currency_to_tag(tag)
    r = gtm.accounts().containers().workspaces().tags().update(
        path=f"{WS}/tags/{TAG_FORM_ID}", body=new_tag
    ).execute()
    print(f"[UPDATE] Tag '{r['name']}' (form) - {len(r['parameter'][1]['list'])} event params")

    # 4. Update tag phone click
    tag = gtm.accounts().containers().workspaces().tags().get(
        path=f"{WS}/tags/{TAG_PHONE_ID}"
    ).execute()
    new_tag = add_value_currency_to_tag(tag)
    r = gtm.accounts().containers().workspaces().tags().update(
        path=f"{WS}/tags/{TAG_PHONE_ID}", body=new_tag
    ).execute()
    print(f"[UPDATE] Tag '{r['name']}' (phone) - {len(r['parameter'][1]['list'])} event params")

    # 5. Create version (do not publish)
    notes = "Dynamic conv_value: Lookup Table 'Lead Value by URL' + Currency PLN, dodane value+currency do tagow generate_lead (form + phone)."
    ver = gtm.accounts().containers().workspaces().create_version(
        path=WS, body={"name": "conv_value dynamic", "notes": notes}
    ).execute()
    if ver.get("containerVersion"):
        v = ver["containerVersion"]
        print(f"\n[VERSION CREATED] {v['containerVersionId']} | {v['name']}")
        print(f"Preview / Publish: https://tagmanager.google.com/#/container/accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}/versions/{v['containerVersionId']}")
    else:
        print(f"\n[VERSION] unexpected response: {ver}")


if __name__ == "__main__":
    try:
        main()
    except HttpError as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        sys.exit(1)
