#!/usr/bin/env bash
# First-time installation only; refuses to replace an existing service.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
app=/opt/teslamate-app
unit_dir=/etc/systemd/system
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
if [ -e "$unit_dir/tesla-app-sync.service" ] || [ -e "$app/sync_drives.py" ]; then
  echo 'Existing sync installation found. Stop here and use the documented backup/upgrade procedure.' >&2
  exit 1
fi
[ -f "$app/supabase.json" ] || { echo 'Create private backend configuration first.' >&2; exit 1; }
python3 - "$root" <<'PY'
import json,sys,urllib.request
sys.path.insert(0,sys.argv[1]+'/backend')
from configuration import validate_config
c=validate_config(json.load(open('/opt/teslamate-app/supabase.json')),require_key=True)
# Check all migrated app tables before installing anything.
for table in ('app_drives','app_drive_details','app_vehicles','app_sync_status'):
    r=urllib.request.Request(c['url']+'/rest/v1/'+table+'?select=owner_id&limit=0',
        headers={'apikey':c['service_role_key'],'Authorization':'Bearer '+c['service_role_key']})
    with urllib.request.urlopen(r,timeout=30) as p:
        if p.status != 200:raise RuntimeError('Migration preflight failed')
print('Configuration and migration preflight passed.')
PY
install -d -m 700 "$app/licenses"
for name in configuration.py sync_drives.py sync_details.py sync_vehicles.py drive_details.py geocode_drives.py; do
  install -m 600 "$root/backend/$name" "$app/$name"
done
install -m 600 "$root/backend/licenses/coordtransform-MIT.txt" "$app/licenses/coordtransform-MIT.txt"
for name in tesla-app-sync.service tesla-app-sync.timer tesla-app-geocode.service tesla-app-geocode.timer; do
  install -m 644 "$root/backend/$name" "$unit_dir/$name"
done
systemctl daemon-reload
# On failure, timer remains disabled; diagnose and retry the service manually.
systemctl start tesla-app-sync.service
systemctl enable --now tesla-app-sync.timer
printf '%s\n' 'Sync installed. Optional Amap timer is NOT enabled.'
