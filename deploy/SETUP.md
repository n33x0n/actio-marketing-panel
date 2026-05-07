# Deployment — Mikrus VPS

## Wymagania

- Mikrus VPS (Pro / Pro Max)
- SSH dostęp (klucze)
- Python 3.12 (jest domyślnie na Mikrusie)
- Dostęp do panelu Mikrus (do dodania udostępnionego portu)
- Konto Cloudflare z domeną (do auth via Cloudflare Tunnel + Access)

## Pierwsza instalacja

### 1. Mikrus — przygotowanie

```bash
# SSH na Mikrus
ssh root@srvNN.mikr.us -p 10NNN

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

# Klon repo
mkdir -p /opt && cd /opt
git clone https://github.com/n33x0n/actio-marketing-panel.git
cd actio-marketing-panel

# Sync deps
uv sync

# Katalogi runtime
mkdir -p /opt/actio-marketing-panel/.gcp
mkdir -p /opt/actio-marketing-panel/md-reports
mkdir -p /opt/actio-marketing-panel/logs
```

### 2. Sekrety (kopia z lokalnego macOS)

```bash
# Z lokalnego maca:
scp ~/.gcp/actio-ga4.json ra:/opt/actio-marketing-panel/.gcp/actio-ga4.json
scp .env ra:/opt/actio-marketing-panel/.env
scp .mcp.json ra:/opt/actio-marketing-panel/.mcp.json
scp marketing_data.db ra:/opt/actio-marketing-panel/marketing_data.db
```

### 3. Update ścieżek na mikrusie

```bash
ssh ra "cd /opt/actio-marketing-panel && python3 -c \"
import json, pathlib
p = pathlib.Path('.mcp.json')
cfg = json.loads(p.read_text())
env = cfg['mcpServers']['actio-marketing']['env']
env['DB_PATH'] = '/opt/actio-marketing-panel/marketing_data.db'
env['GOOGLE_APPLICATION_CREDENTIALS'] = '/opt/actio-marketing-panel/.gcp/actio-ga4.json'
env['MD_REPORTS_DIR'] = '/opt/actio-marketing-panel/md-reports'
cfg['mcpServers']['actio-marketing']['cwd'] = '/opt/actio-marketing-panel'
p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
\""
```

### 4. Chainlit panel — systemd

```bash
ssh ra "
  cp /opt/actio-marketing-panel/deploy/actio-chainlit.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now actio-chainlit.service
  systemctl status actio-chainlit
"
```

### 5. Daily report — systemd timer (zastępuje launchd)

```bash
ssh ra "
  cp /opt/actio-marketing-panel/deploy/actio-daily-report.service /etc/systemd/system/
  cp /opt/actio-marketing-panel/deploy/actio-daily-report.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now actio-daily-report.timer
  systemctl list-timers actio-daily-report
"
```

### 6. Cloudflare Tunnel + Access (auth)

Patrz `deploy/CLOUDFLARE.md` (TODO).

## Update kodu po zmianach

```bash
ssh ra "cd /opt/actio-marketing-panel && git pull && uv sync && systemctl restart actio-chainlit"
```

## Logi

- Chainlit: `/opt/actio-marketing-panel/logs/chainlit.log`
- Daily report: `/opt/actio-marketing-panel/logs/daily-report.log`
- systemd: `journalctl -u actio-chainlit -f` lub `journalctl -u actio-daily-report -f`
