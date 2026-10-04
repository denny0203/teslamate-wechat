"""Atomic private drive-detail snapshots. Source DB remains read-only.

No raw points, URLs, credentials or addresses are printed. At most five
changed details are published per invocation; backlog drains on timer runs.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from drive_details import build_detail, PROCESSOR_VERSION
from sync_drives import push
from configuration import validate_config


def source_query(active):
    ids = ','.join(str(int(i)) for i in active) or 'NULL'
    return """
SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
 SELECT d.id, d.car_id,
 to_char(d.start_date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS started_at,
 to_char(d.end_date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS ended_at,
 NULLIF(a.display_name,'') AS start_address, NULLIF(b.display_name,'') AS end_address,
 CASE WHEN d.distance >= 0 AND d.distance < 'Infinity'::float8 THEN d.distance END AS distance_km,
 d.speed_max, d.start_rated_range_km AS start_range_km, d.end_rated_range_km AS end_range_km,
 d.inside_temp_avg, d.outside_temp_avg, c.efficiency AS car_efficiency,
 sp.battery_level AS start_battery, ep.battery_level AS end_battery,
 CASE WHEN sp.id IS NOT NULL THEN json_build_object('latitude',sp.latitude,'longitude',sp.longitude) END AS start_point,
 CASE WHEN ep.id IS NOT NULL THEN json_build_object('latitude',ep.latitude,'longitude',ep.longitude) END AS end_point,
 (SELECT coalesce(json_agg(json_build_object('id',p.id,
 'date',to_char(p.date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
 'latitude',p.latitude,'longitude',p.longitude) ORDER BY p.date,p.id),'[]'::json)
 FROM positions p WHERE p.drive_id=d.id AND p.car_id=d.car_id) AS positions
 FROM drives d
 LEFT JOIN cars c ON c.id=d.car_id
 LEFT JOIN addresses a ON a.id=d.start_address_id
 LEFT JOIN addresses b ON b.id=d.end_address_id
 LEFT JOIN positions sp ON sp.id=d.start_position_id AND sp.car_id=d.car_id AND sp.drive_id=d.id
 LEFT JOIN positions ep ON ep.id=d.end_position_id AND ep.car_id=d.car_id AND ep.drive_id=d.id
 WHERE d.start_date <= (now() AT TIME ZONE 'UTC')
 AND (d.start_date >= ((now()-interval '8 days') AT TIME ZONE 'UTC') OR d.id IN (%s))
 ORDER BY d.start_date DESC,d.id DESC
) t;
""" % ids


def sync(config, directory, read_source=None, publish=push, history=False):
    config = validate_config(config)
    owner = str(uuid.UUID(config['owner_id']))
    manifest_path = directory / 'details-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest.get('owner_id') != owner or manifest.get('destination') != config['url']:
        manifest = {}
    versions = manifest.get('versions', {})
    if read_source is None:
        def read_source(sql):
            return json.loads(subprocess.run(['docker','compose','exec','-T',
                '-e','PGOPTIONS=-c default_transaction_read_only=on','database',
                'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','teslamate','-d','teslamate','-c',sql],
                cwd='/opt/teslamate',capture_output=True,text=True,timeout=90,check=True).stdout)
    historical=[]
    if history:
        if manifest.get('processor') != PROCESSOR_VERSION:
            versions.clear()
        ids=read_source("SELECT coalesce(json_agg(row_to_json(t)),'[]'::json) FROM (SELECT id FROM drives WHERE end_date IS NOT NULL AND start_date <= (now() AT TIME ZONE 'UTC') ORDER BY start_date DESC,id DESC) t;")
        historical=[r['id'] for r in ids if str(r['id']) not in versions][:5]
    query=source_query(manifest.get('active', [])+historical)
    rows = read_source(query)
    # Preserve tracking before publishing, including old unfinished drives.
    active = [r['id'] for r in rows if not r.get('ended_at')]
    next_manifest = {'destination': config['url'], 'owner_id': owner, 'active': active, 'versions': versions, 'processor': PROCESSOR_VERSION}
    temporary = directory / 'details-manifest.next'
    temporary.write_text(json.dumps(next_manifest)+'\n')
    temporary.replace(manifest_path)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    changed = 0
    for row in rows:
        version = hashlib.sha256((PROCESSOR_VERSION+json.dumps(row,sort_keys=True)).encode()).hexdigest()
        if versions.get(str(row['id'])) == version:
            continue
        if changed >= 5:
            continue
        payload = build_detail(row)
        # Upsert the associated summary first, including tracked drives older than 8 days.
        summary_keys = ['id','car_id','started_at','ended_at','start_address','end_address','distance_km']
        summary = {k:payload['summary'][k] for k in summary_keys}
        publish(config,'app_drives',[dict(summary,owner_id=owner,synced_at=now)],'owner_id,id')
        publish(config,'app_drive_details',[{'owner_id':owner,'id':row['id'],'car_id':row['car_id'],
            'version':version,'status':payload['status'],'payload':payload,'synced_at':now}],'owner_id,id')
        versions[str(row['id'])] = version
        changed += 1
        # Save only after successful publication; failed snapshots are retried.
        temporary = directory / 'details-manifest.next'
        temporary.write_text(json.dumps(next_manifest)+'\n')
        temporary.replace(manifest_path)
    # Prune versions outside current window (active drives are still queried).
    next_manifest['versions'] = versions if history else {str(r['id']): versions[str(r['id'])] for r in rows if str(r['id']) in versions}
    temporary = directory / 'details-manifest.next'
    temporary.write_text(json.dumps(next_manifest)+'\n')
    temporary.replace(manifest_path)
    return {'status':'ok','examined':len(rows),'published':changed,
        'remaining':sum(versions.get(str(r['id'])) != hashlib.sha256((PROCESSOR_VERSION+json.dumps(r,sort_keys=True)).encode()).hexdigest() for r in rows),
        'history_pending':len([r for r in ids if str(r['id']) not in versions]) if history else 0, 'finished_at':now}


def main():
    os.umask(0o077)
    path = Path(sys.argv[1] if len(sys.argv)>1 else '/opt/teslamate-app/supabase.json')
    with open(path.parent/'details.lock','w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            result = sync(json.loads(path.read_text()),path.parent,history=True)
            (path.parent/'last-details-sync.json').write_text(json.dumps(result)+'\n')
            print(json.dumps(result))
        except Exception as error:
            print('Detail sync failed: '+type(error).__name__,file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()
