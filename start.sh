#!/bin/bash
cd /opt/actio-marketing-panel
exec /root/.local/bin/uv run chainlit run app.py --port 44320 --host 0.0.0.0 < /dev/null
