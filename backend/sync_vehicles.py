"""Read-only TeslaMate vehicle snapshots; no vehicle API/control calls."""
import json, subprocess, datetime as dt, os, sys
from pathlib import Path
from sync_drives import push
from configuration import validate_config
QUERY="""
SELECT coalesce(json_agg(row_to_json(v)),'[]'::json) FROM (
SELECT c.id AS car_id,c.name,c.model,c.efficiency,
(SELECT row_to_json(p) FROM (SELECT to_char(date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS sampled_at,
battery_level,rated_battery_range_km,inside_temp,outside_temp FROM positions WHERE car_id=c.id ORDER BY date DESC,id DESC LIMIT 1) p) AS position,
(SELECT row_to_json(s) FROM (SELECT state,to_char(start_date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS started_at FROM states WHERE car_id=c.id ORDER BY start_date DESC,id DESC LIMIT 1) s) AS state,
(SELECT row_to_json(ch) FROM (SELECT cp.id,to_char(cp.start_date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS started_at,
to_char(cp.end_date,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS ended_at,cp.charge_energy_added,
cp.start_battery_level,cp.end_battery_level,cp.start_rated_range_km,cp.end_rated_range_km,a.display_name AS address
FROM charging_processes cp LEFT JOIN addresses a ON a.id=cp.address_id WHERE cp.car_id=c.id AND cp.end_date IS NOT NULL
ORDER BY cp.end_date DESC,cp.id DESC LIMIT 1) ch) AS charge
FROM cars c ORDER BY c.id) v;
"""
def sync(config):
 config = validate_config(config)
 raw=subprocess.run(['docker','compose','exec','-T','-e','PGOPTIONS=-c default_transaction_read_only=on','database','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','teslamate','-d','teslamate','-c',QUERY],cwd='/opt/teslamate',capture_output=True,text=True,check=True,timeout=60).stdout
 rows=json.loads(raw);now=dt.datetime.now(dt.timezone.utc).isoformat()
 push(config,'app_vehicles',[{'owner_id':config['owner_id'],'car_id':r['car_id'],'payload':r,'synced_at':now} for r in rows],'owner_id,car_id')
 return {'status':'ok','vehicles':len(rows),'finished_at':now}
if __name__=='__main__':
 os.umask(0o077)
 try:
  path=Path(sys.argv[1] if len(sys.argv)>1 else '/opt/teslamate-app/supabase.json')
  result=sync(json.loads(path.read_text()));(path.parent/'last-vehicles-sync.json').write_text(json.dumps(result));print(json.dumps(result))
 except Exception as e: print('Vehicle sync failed: '+type(e).__name__,file=sys.stderr);sys.exit(1)
