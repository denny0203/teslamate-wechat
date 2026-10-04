"""Run on the TeslaMate ECS. Source SQL is read-only; only app tables are upserted."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error
import uuid

from configuration import validate_config
QUERY = """
SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
 SELECT d.id, d.car_id,
   to_char(d.start_date, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS started_at,
   CASE WHEN d.end_date IS NOT NULL THEN to_char(d.end_date, 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END AS ended_at,
   NULLIF(a.display_name, '') AS start_address,
   NULLIF(b.display_name, '') AS end_address,
   CASE WHEN d.distance >= 0 AND d.distance < 'Infinity'::float8 THEN d.distance END AS distance_km,
 CASE WHEN d.end_date IS NOT NULL AND d.start_rated_range_km >= d.end_rated_range_km AND c.efficiency > 0 THEN (d.start_rated_range_km-d.end_rated_range_km)*c.efficiency END AS energy_used_kwh,
 CASE WHEN d.end_date IS NOT NULL AND d.start_rated_range_km >= d.end_rated_range_km THEN d.start_rated_range_km-d.end_rated_range_km END AS range_used_km
 FROM drives d
 LEFT JOIN cars c ON c.id=d.car_id
 LEFT JOIN addresses a ON a.id = d.start_address_id
 LEFT JOIN addresses b ON b.id = d.end_address_id
 WHERE d.start_date <= (now() AT TIME ZONE 'UTC')
   AND (d.end_date IS NOT NULL OR d.start_date >= ((now()-interval '8 days') AT TIME ZONE 'UTC'))
 ORDER BY d.start_date DESC, d.id DESC
) t;
"""

def push(config, table, records, conflict):
    config = validate_config(config, require_key=True)
    req = urllib.request.Request(config['url'] + '/rest/v1/' + table + '?on_conflict=' + conflict,
        data=json.dumps(records, allow_nan=False).encode(), method='POST',
        headers={'apikey': config['service_role_key'], 'Authorization': 'Bearer ' + config['service_role_key'],
                 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal'})
    with urllib.request.urlopen(req, timeout=40) as response:
        if response.status not in (200, 201, 204): raise RuntimeError('Unexpected API status')

def sync(config):
    config = validate_config(config)
    owner = str(uuid.UUID(config['owner_id']))
    raw = subprocess.run(['docker', 'compose', 'exec', '-T', '-e', 'PGOPTIONS=-c default_transaction_read_only=on',
        'database', 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'teslamate', '-d', 'teslamate', '-c', QUERY],
        cwd='/opt/teslamate', capture_output=True, text=True, timeout=60, check=True).stdout
    rows = json.loads(raw)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for row in rows:
        row['owner_id'] = owner
        row['synced_at'] = now
    for start in range(0, len(rows), 200):
        push(config, 'app_drives', rows[start:start + 200], 'owner_id,id')
    latest = max((row['started_at'] for row in rows), default=None)
    push(config, 'app_sync_status', [{'owner_id': owner, 'last_success_at': now,
        'latest_drive_at': latest, 'synced_rows': len(rows)}], 'owner_id')
    return {'status': 'ok', 'rows': len(rows), 'last_success_at': now, 'latest_drive_at': latest}

def main():
    os.umask(0o077)
    path = Path(sys.argv[1] if len(sys.argv) > 1 else '/opt/teslamate-app/supabase.json')
    with open(path.parent / 'sync.lock', 'w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        try:
            result = sync(json.loads(path.read_text()))
            (path.parent / 'last-sync.json').write_text(json.dumps(result) + '\n')
            print(json.dumps(result))
        except urllib.error.HTTPError as error:
            print('Sync failed: HTTP ' + str(error.code), file=sys.stderr)
            sys.exit(1)
        except Exception as error:
            # Do not log exception text: it may carry SQL records or request material.
            print('Sync failed: ' + type(error).__name__, file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__': main()
