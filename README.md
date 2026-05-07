# actio-marketing-panel

Marketing Intelligence panel dla Actio (B2B VoIP) — synchronizacja GA4 / Google Search Console / Google Ads do lokalnej bazy SQLite, codzienny raport CMO generowany przez LLM (Opus 4.7), wysyłka email + Pushover, dashboard Chainlit, alerty progowe.

**Stack**: Python 3.12 · uv · SQLite · MCP (stdio) · Chainlit · Plotly · Google Ads API v22 · GA4 Data API · GSC API · Anthropic Claude (via OpenRouter) · Pushover · Gmail SMTP.

## Funkcjonalność

### Pipeline danych
- **GA4** — sesje, użytkownicy, konwersje per `sessionSourceMedium` (7 dni okno)
- **GA4 leady per landing** — `generate_lead` per landingPage + source (atrybucja paid → landing → lead)
- **GSC** — wszystkie property, granularność `date × query × page` (3-day lag)
- **Google Ads** — kampanie / keywordy / search terms / Lost IS / customer assets performance
- **SQLite** jako jedno źródło prawdy (WAL mode, idempotent upserts po kluczach naturalnych)

### Raport CMO
- Codzienny raport o 7:00 (launchd lokalnie / systemd timer na VPS)
- Prompt z **live state konta** (eliminacja halucynacji modelu) + week-over-week porównanie
- Wysyłka mailem do dwóch grup: **CMO** (pełny raport z rekomendacjami) i **CEO** (raport bez sekcji Rekomendacje)
- Push notification przez Pushover
- Markdown raport zapisywany lokalnie (`md-reports/` lub Obsidian vault)

### Alerty
- CPA > 50 zł na kampanii
- Dry spend (≥ 50 klików, 0 konwersji w 7 dniach)
- Policy issues (RSA / asset DISAPPROVED lub APPROVED_LIMITED)
- Wszystkie wysyłane jako Pushover priority=2 (dźwiękowy emergency push)

### MCP server (Claude Code integration)
12 narzędzi udostępnionych przez `mcp_server.py`:
- `sync_ga4_data`, `sync_gsc_data`, `sync_ads_data`, `sync_ads_keywords`, `sync_ads_search_terms`
- `query_history`, `query_gsc`, `query_ads_campaigns`, `query_ads_keywords`, `query_ads_search_terms`
- `generate_report`

### Chainlit panel
Web UI dostępny na `localhost:9999` — przegląd historii konwersji + wykresy trendów.

## Architektura modułów

| Moduł | Rola |
|---|---|
| `db.py` | SQLite layer: schema, init, upsert, fetch, migracje ALTER TABLE |
| `ga4.py` | GA4 Data API wrapper (sessions per source/medium, leady per landing) |
| `gsc.py` | Google Search Console API (multi-site, paginacja) |
| `ads.py` | Google Ads API v22 (kampanie z Lost IS, keywordy z QS, search terms, live state, asset performance) |
| `analyze.py` | Orchestracja: sync → DB → LLM prompt → save → mail → push → alerty |
| `email_sender.py` | Gmail SMTP, dwie grupy odbiorców (CMO/CEO), markdown → HTML |
| `alerts.py` | Threshold-based alerty + policy check, Pushover priority=2 |
| `mcp_server.py` | Serwer MCP stdio (12 tools) |
| `app.py` | Chainlit panel |

## Setup

Patrz `deploy/SETUP.md` (deployment na Mikrus przez Cloudflare Tunnel + Access).

Do lokalnego rozwoju:

```bash
# 1. uv (jeśli brak)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync deps
uv sync

# 3. Service Account GA4 (jednorazowo)
mkdir -p ~/.gcp
# Pobierz JSON z Google Cloud Console, przenieś do ~/.gcp/actio-ga4.json
chmod 600 ~/.gcp/actio-ga4.json

# 4. Konfiguracja sekretnych env vars
cp .env.example .env
cp .mcp.json.example .mcp.json
# Wypełnij wartości w obu plikach

# 5. Init bazy
uv run python -c "import db, os, json; cfg = json.load(open('.mcp.json')); [os.environ.setdefault(k,v) for k,v in cfg['mcpServers']['actio-marketing']['env'].items()]; db.init_db(os.environ['DB_PATH']); print('OK')"

# 6. Pierwszy sync (przez MCP w Claude Code lub CLI)
uv run python -c "import analyze; print(analyze.run_all_syncs())"

# 7. Generate report
uv run python -c "import analyze; r = analyze.generate_report(); print(r['vault_path'])"

# 8. Chainlit panel
uv run chainlit run app.py --port 9999 --host 127.0.0.1
```

## Sekrety i bezpieczeństwo

- `.env` i `.mcp.json` zawierają wrażliwe dane (Google Ads developer token, OAuth secrets, Gmail App Password, Pushover tokens, OpenRouter API key) — **nigdy nie commit'ować** (są w `.gitignore`)
- Service Account credentials (`~/.gcp/actio-ga4.json` lub `.gcp/` w projekcie) — j.w.
- `marketing_data.db` zawiera dane biznesowe — `.gitignore`'d
- Templates do skopiowania: `.env.example`, `.mcp.json.example`

## OAuth Google Ads

Refresh token generowany jednorazowo skryptem `scripts/get_ads_refresh_token.py`. Po publikacji OAuth client w GCP w trybie **Production** token jest długoterminowy. Tryb **Testing** = wygaśnie po 7 dniach.

## Deployment

Deployment na Mikrus VPS przez Cloudflare Tunnel + Cloudflare Access (auth via whitelist email). Pełna instrukcja: `deploy/SETUP.md`.

## Licencja

Apache License 2.0 — patrz [LICENSE](LICENSE).

## Autor

Tom Lebioda · hello@tomlebioda.com
