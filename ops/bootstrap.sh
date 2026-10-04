#!/usr/bin/env bash
# Fresh Linux host only. Generates secrets locally without printing them.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run as root on your deployment host.' >&2; exit 1; }
source_dir="$(cd "$(dirname "$0")" && pwd)"
if [ -e /opt/teslamate/compose.yaml ] || [ -e /opt/teslamate/.env ]; then
  echo 'Existing TeslaMate installation found. Follow the manual upgrade/backup procedure.' >&2
  exit 1
fi
command -v docker >/dev/null
docker compose version >/dev/null
install -d -m 700 /opt/teslamate /opt/teslamate/backups
install -d -m 755 /opt/teslamate/import
install -m 600 "$source_dir/compose.yaml" /opt/teslamate/compose.yaml
python3 - <<'PY'
import os,secrets
fd=os.open('/opt/teslamate/.env',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as handle:
    for name in ('ENCRYPTION_KEY','DATABASE_PASS','GRAFANA_ADMIN_PASSWORD'):
        handle.write(name+'='+secrets.token_hex(32)+'\n')
print('Generated private .env; secret values not displayed.')
PY
cd /opt/teslamate
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
