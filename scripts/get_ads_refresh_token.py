"""Jednorazowy OAuth flow — generuje refresh_token dla Google Ads API.

Użycie:
    uv run python scripts/get_ads_refresh_token.py

Otwiera przeglądarkę, prosisz o autoryzację konta tlebioda@gmail.com,
skrypt wypisuje refresh_token na stdout. Wklej go do .mcp.json jako
GOOGLE_ADS_REFRESH_TOKEN.
"""
from __future__ import annotations

import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow


OAUTH_JSON = os.path.expanduser("~/.gcp/actio-ads-oauth.json")
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> None:
    if not os.path.exists(OAUTH_JSON):
        sys.exit(f"ERROR: brak pliku {OAUTH_JSON}")

    flow = InstalledAppFlow.from_client_secrets_file(OAUTH_JSON, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print()
    print("=" * 60)
    print("REFRESH TOKEN (wklej do .mcp.json jako GOOGLE_ADS_REFRESH_TOKEN):")
    print()
    print(creds.refresh_token)
    print("=" * 60)

    with open(OAUTH_JSON) as f:
        oauth = json.load(f)["installed"]
    print()
    print("CLIENT_ID:    ", oauth["client_id"])
    print("CLIENT_SECRET:", oauth["client_secret"])


if __name__ == "__main__":
    main()
