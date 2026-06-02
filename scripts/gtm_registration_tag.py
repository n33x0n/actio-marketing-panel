"""GTM: trigger + tag dla rejestracja-demo.actio.pl/registration_confirm/*

Strona potwierdzenia rejestracji konta jest SPA (Vue/Laravel) bez konwersji.
Po wklejeniu containera GTM-56N7NT77 do <head>, ten tag wystrzeli sign_up
jako generate_lead z value=1500, currency=PLN, lead_type=registration.
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
WORKSPACE_ID = "10"
WS = f"accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}/workspaces/{WORKSPACE_ID}"
MEASUREMENT_ID = "G-W864FFJXKQ"
REG_VALUE = "1500"

TRIGGER_NAME = "Page View - Registration Confirm"
TAG_NAME = "GA4 - generate lead - registration"


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


def trigger_body() -> dict:
    return {
        "name": TRIGGER_NAME,
        "type": "pageview",
        "filter": [
            {
                "type": "matchRegex",
                "parameter": [
                    {"type": "template", "key": "arg0", "value": "{{Page URL}}"},
                    {
                        "type": "template",
                        "key": "arg1",
                        "value": r"^https?://rejestracja(-demo)?\.actio\.pl/registration_confirm/",
                    },
                ],
            }
        ],
    }


def tag_body(trigger_id: str) -> dict:
    return {
        "name": TAG_NAME,
        "type": "gaawe",
        "parameter": [
            {"type": "boolean", "key": "sendEcommerceData", "value": "false"},
            {
                "type": "list",
                "key": "eventSettingsTable",
                "list": [
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "lead_type"},
                            {"type": "template", "key": "parameterValue", "value": "registration"},
                        ],
                    },
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "value"},
                            {"type": "template", "key": "parameterValue", "value": REG_VALUE},
                        ],
                    },
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "currency"},
                            {"type": "template", "key": "parameterValue", "value": "PLN"},
                        ],
                    },
                    {
                        "type": "map",
                        "map": [
                            {"type": "template", "key": "parameter", "value": "form_location"},
                            {"type": "template", "key": "parameterValue", "value": "{{Page Path}}"},
                        ],
                    },
                ],
            },
            {"type": "template", "key": "eventName", "value": "generate_lead"},
            {"type": "template", "key": "measurementIdOverride", "value": MEASUREMENT_ID},
        ],
        "firingTriggerId": [trigger_id],
        "tagFiringOption": "oncePerEvent",
    }


def find_by_name(items: list, name: str):
    for it in items:
        if it.get("name") == name:
            return it
    return None


def main():
    with open(".mcp.json") as f:
        env = json.load(f)["mcpServers"]["actio-marketing"]["env"]
    os.environ.update(env)

    gtm = gtm_client()

    # 1. Trigger
    triggers = gtm.accounts().containers().workspaces().triggers().list(parent=WS).execute().get("trigger", [])
    existing = find_by_name(triggers, TRIGGER_NAME)
    body = trigger_body()
    if existing:
        body["triggerId"] = existing["triggerId"]
        body["fingerprint"] = existing["fingerprint"]
        r = gtm.accounts().containers().workspaces().triggers().update(
            path=existing["path"], body=body
        ).execute()
        print(f"[UPDATE] Trigger '{TRIGGER_NAME}' -> {r['triggerId']}")
    else:
        r = gtm.accounts().containers().workspaces().triggers().create(parent=WS, body=body).execute()
        print(f"[CREATE] Trigger '{TRIGGER_NAME}' -> {r['triggerId']}")
    trigger_id = r["triggerId"]

    # 2. Tag
    tags = gtm.accounts().containers().workspaces().tags().list(parent=WS).execute().get("tag", [])
    existing = find_by_name(tags, TAG_NAME)
    body = tag_body(trigger_id)
    if existing:
        body["tagId"] = existing["tagId"]
        body["fingerprint"] = existing["fingerprint"]
        r = gtm.accounts().containers().workspaces().tags().update(
            path=existing["path"], body=body
        ).execute()
        print(f"[UPDATE] Tag '{TAG_NAME}' -> {r['tagId']}")
    else:
        r = gtm.accounts().containers().workspaces().tags().create(parent=WS, body=body).execute()
        print(f"[CREATE] Tag '{TAG_NAME}' -> {r['tagId']}")

    # 3. Create version
    notes = (
        "Registration tracking: nowy trigger 'Page View - Registration Confirm' "
        "(URL matches ^https?://rejestracja-demo\\.actio\\.pl/registration_confirm/) "
        "+ nowy tag GA4 'generate lead - registration' (value=1500, currency=PLN, "
        "lead_type=registration, form_location={{Page Path}}). "
        "Wymaga wklejenia containera GTM-56N7NT77 do <head> aplikacji Odbieraczka."
    )
    ver = gtm.accounts().containers().workspaces().create_version(
        path=WS, body={"name": "registration tracking", "notes": notes}
    ).execute()
    if ver.get("containerVersion"):
        v = ver["containerVersion"]
        print(f"\n[VERSION CREATED] {v['containerVersionId']} | {v['name']}")
        ver_path = f"accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}/versions/{v['containerVersionId']}"

        # 4. Publish
        pub = gtm.accounts().containers().versions().publish(path=ver_path).execute()
        print(f"[PUBLISHED] version {pub['containerVersion']['containerVersionId']}")
        print(f"Compiler errors: {pub.get('compilerError')}")
    else:
        print(f"\n[VERSION] unexpected: {ver}")


if __name__ == "__main__":
    try:
        main()
    except HttpError as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        sys.exit(1)
