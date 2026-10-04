"""Optional disposable PostgreSQL check. Synthetic data, private socket, no cloud access.
Requires PostgreSQL server binaries and pg_config in PATH. Does not read backups.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sync_details import source_query
from sync_drives import QUERY as HISTORY_QUERY
from sync_vehicles import QUERY as VEHICLE_QUERY
ROOT = Path(__file__).resolve().parents[1]


def verify():
    bindir = Path(subprocess.check_output(['pg_config', '--bindir'], text=True).strip())
    with tempfile.TemporaryDirectory(prefix='tesla-public-sql-') as temp:
        folder = Path(temp)
        database = folder / 'db'
        subprocess.run([str(bindir/'initdb'), '-D', str(database), '-A', 'trust', '--no-locale'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        running = False
        try:
            subprocess.run([str(bindir/'pg_ctl'), '-D', str(database), '-l', str(folder/'pg.log'),
                            '-o', "-k " + str(folder) + " -c listen_addresses=''", '-w', 'start'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            running = True
            def sql(text):
                return subprocess.run([str(bindir/'psql'), '-h', str(folder), '-d', 'postgres',
                                       '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'],
                                      input=text, text=True, capture_output=True, check=True).stdout.strip()
            sql("""CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
GRANT USAGE ON SCHEMA auth TO authenticated;
""")
            for _ in range(2):
                for name in ('001_app_schema.sql','002_drive_details.sql','003_vehicle_history.sql'):
                    sql((ROOT/'backend'/name).read_text())
            owners = ['00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002']
            sql("""INSERT INTO auth.users VALUES ('00000000-0000-0000-0000-000000000001'),('00000000-0000-0000-0000-000000000002');
INSERT INTO app_drives(owner_id,id,car_id,started_at) SELECT id,1,1,now() FROM auth.users;
INSERT INTO app_drive_details(owner_id,id,car_id,version,status,payload) SELECT id,1,1,'v1','ready','{}' FROM auth.users;
INSERT INTO app_vehicles(owner_id,car_id,payload) SELECT id,1,'{}' FROM auth.users;
INSERT INTO app_sync_status(owner_id,last_success_at,synced_rows) SELECT id,now(),1 FROM auth.users;
""")
            for table in ('app_drives','app_drive_details','app_vehicles','app_sync_status'):
                assert sql("SELECT relrowsecurity FROM pg_class WHERE oid='"+table+"'::regclass;") == 't'
                for role in ('anon','authenticated'):
                    for privilege in ('INSERT','UPDATE','DELETE'):
                        assert sql("SELECT has_table_privilege('"+role+"','"+table+"','"+privilege+"');") == 'f'
                assert sql("SELECT has_table_privilege('anon','"+table+"','SELECT');") == 'f'
                for owner in owners:
                    result = sql("SET ROLE authenticated; SET request.jwt.claim.sub='"+owner+"'; SELECT count(*),min(owner_id::text) FROM "+table+"; RESET ROLE;")
                    assert result == '1|' + owner
                assert sql("SET ROLE authenticated; SET request.jwt.claim.sub='00000000-0000-0000-0000-000000000003'; SELECT count(*) FROM "+table+"; RESET ROLE;") == '0'
            # Minimal synthetic source schema matching fields used by the queries.
            sql("""CREATE TABLE cars(id bigint, name text, model text, efficiency double precision);
CREATE TABLE addresses(id bigint, display_name text);
CREATE TABLE drives(id bigint,car_id bigint,start_date timestamp,end_date timestamp,
 start_address_id bigint,end_address_id bigint,start_position_id bigint,end_position_id bigint,
 distance double precision,speed_max double precision,start_rated_range_km double precision,
 end_rated_range_km double precision,inside_temp_avg double precision,outside_temp_avg double precision);
CREATE TABLE positions(id bigint,car_id bigint,drive_id bigint,date timestamp,latitude double precision,
 longitude double precision,battery_level integer,rated_battery_range_km double precision,
 inside_temp double precision,outside_temp double precision);
CREATE TABLE states(car_id bigint,state text,start_date timestamp);
CREATE TABLE charging_processes(id bigint,car_id bigint,start_date timestamp,end_date timestamp,
 charge_energy_added double precision,start_battery_level integer,end_battery_level integer,
 start_rated_range_km double precision,end_rated_range_km double precision,address_id bigint);
INSERT INTO cars VALUES(1,'Test car','3',0.14);
INSERT INTO drives(id,car_id,start_date,end_date,start_position_id,end_position_id,distance)
 VALUES(7,1,(now()-interval '10 minutes') AT TIME ZONE 'UTC',now() AT TIME ZONE 'UTC',8,9,5);
INSERT INTO positions(id,car_id,drive_id,date,latitude,longitude,battery_level)
 VALUES(8,1,7,(now()-interval '10 minutes') AT TIME ZONE 'UTC',30,120,80),
 (9,1,7,now() AT TIME ZONE 'UTC',30.01,120.01,79),
 (10,2,7,now() AT TIME ZONE 'UTC',30,120,50);
""")
            rows = json.loads(sql(source_query([])))
            history = json.loads(sql(HISTORY_QUERY))
            vehicles = json.loads(sql(VEHICLE_QUERY))
            assert len(rows) == len(history) == len(vehicles) == 1
            assert len(rows[0]['positions']) == 2
            assert rows[0]['start_battery'] == 80 and rows[0]['end_battery'] == 79
            assert vehicles[0]['position']['battery_level'] == 79
            return {'migrations_twice': True, 'rls_four_tables': True,
                    'source_queries_synthetic': True, 'source_car_isolation': True}
        finally:
            if running:
                subprocess.run([str(bindir/'pg_ctl'), '-D', str(database), '-m', 'immediate', 'stop'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)


if __name__ == '__main__':
    try:
        print(json.dumps(verify()))
    except Exception as error:
        print('Local SQL verification failed: '+type(error).__name__, file=sys.stderr)
        sys.exit(1)
