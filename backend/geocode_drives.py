"""Fill missing, completed drive endpoints from Amap; never overwrite GPS or existing links.

Run only on the authorized ECS. Credentials, coordinates, addresses and request URLs
are deliberately excluded from stdout, exceptions and systemd logs.
"""
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

PROVIDER = 'tesla-app-amap-v1'
QUERY = """
SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
 SELECT d.id, e.side, p.id AS position_id, p.latitude, p.longitude
 FROM drives d
 CROSS JOIN LATERAL (VALUES
 ('start', d.start_position_id, d.start_address_id),
 ('end', d.end_position_id, d.end_address_id)) e(side, position_id, address_id)
 JOIN positions p ON p.id=e.position_id AND p.car_id=d.car_id
 WHERE e.address_id IS NULL AND d.end_date IS NOT NULL
 AND d.start_date <= (now() AT TIME ZONE 'UTC')
 AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
 ORDER BY d.start_date DESC, d.id DESC, e.side LIMIT 40
) t;
"""

class GeocodeError(Exception): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise GeocodeError('redirect_refused')

def api(key, path, params):
    req = urllib.request.Request('https://restapi.amap.com' + path + '?' +
        urllib.parse.urlencode(dict(params, key=key, output='JSON')),
        headers={'User-Agent': 'TeslaApp-private-geocoder/1.0'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
        payload = json.load(response)
    if payload.get('status') != '1':
        code = str(payload.get('infocode', ''))
        raise GeocodeError(code if re.fullmatch(r'\d{5}', code) else 'api_failure')
    return payload

def text(value):
    return value.strip() if isinstance(value, str) else ''

def valid_point(lat, lon):
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise GeocodeError('invalid_coordinates')
    return lat, lon

def reverse(key, lat, lon, request=api):
    lat, lon = valid_point(lat, lon)
    # GPS coordinates must be converted by the provider before reverse lookup.
    converted = request(key, '/v3/assistant/coordinate/convert',
        {'locations': f'{lon:.6f},{lat:.6f}', 'coordsys': 'gps'})
    location = converted.get('locations', '')
    if not isinstance(location, str) or not re.fullmatch(r'-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?', location):
        raise GeocodeError('invalid_conversion')
    x, y = map(float, location.split(','))
    valid_point(y, x)
    payload = request(key, '/v3/geocode/regeo',
        {'location': f'{x:.6f},{y:.6f}', 'extensions': 'base', 'radius': '100'})
    geo = payload.get('regeocode')
    if not isinstance(geo, dict) or not text(geo.get('formatted_address')):
        raise GeocodeError('empty_address')
    component = geo.get('addressComponent') or {}
    street = component.get('streetNumber') or {}
    if not isinstance(component, dict) or not isinstance(street, dict):
        raise GeocodeError('invalid_address')
    return {'display_name': text(geo['formatted_address'])[:512],
        'latitude': lat, 'longitude': lon,
        'road': text(street.get('street')), 'house_number': text(street.get('number')),
        'city': text(component.get('city')) or text(component.get('province')),
        'county': text(component.get('district')), 'state': text(component.get('province')),
        'country': text(component.get('country')),
        'raw': {'provider': PROVIDER, 'coordinate_system': 'wgs84', 'regeocode': geo}}

def sql_literal(value):
    # SQL travels only through stdin, with standard_conforming_strings enforced.
    return "'" + str(value).replace("'", "''") + "'"

def psql(query, readonly=False):
    command = ['docker', 'compose', 'exec', '-T']
    if readonly: command += ['-e', 'PGOPTIONS=-c default_transaction_read_only=on']
    command += ['database', 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'teslamate', '-d', 'teslamate']
    result = subprocess.run(command, input='SET standard_conforming_strings=on;\n'+query,
        cwd='/opt/teslamate', capture_output=True, text=True, timeout=60)
    if result.returncode: raise GeocodeError('database_failure')
    return result.stdout.strip()

def fill_sql(endpoint, attrs):
    side = endpoint['side']
    if side not in ('start', 'end'): raise ValueError('Invalid endpoint side')
    ident, pos = int(endpoint['id']), int(endpoint['position_id'])
    lat, lon = valid_point(endpoint['latitude'], endpoint['longitude'])
    fields = ['display_name', 'latitude', 'longitude', 'road', 'house_number', 'city', 'county', 'state', 'country', 'raw']
    values = [sql_literal(json.dumps(attrs[f], ensure_ascii=False))+'::jsonb' if f == 'raw'
        else sql_literal(attrs[f]) for f in fields]
    # Lock and compare the endpoint again: a native lookup may have completed meanwhile.
    return f"""BEGIN;
SELECT pg_advisory_xact_lock(712309);
WITH target AS (
 SELECT id FROM drives WHERE id={ident} AND {side}_address_id IS NULL
 AND {side}_position_id={pos} AND end_date IS NOT NULL FOR UPDATE
), existing AS (
 SELECT id FROM addresses WHERE latitude={lat} AND longitude={lon}
 AND raw->>'provider'={sql_literal(PROVIDER)} ORDER BY id LIMIT 1
), added AS (
 INSERT INTO addresses ({','.join(fields)},inserted_at,updated_at)
 SELECT {','.join(values)},now() AT TIME ZONE 'UTC',now() AT TIME ZONE 'UTC'
 WHERE EXISTS(SELECT 1 FROM target) AND NOT EXISTS(SELECT 1 FROM existing)
 RETURNING id
), chosen AS (SELECT id FROM existing UNION ALL SELECT id FROM added)
UPDATE drives SET {side}_address_id=chosen.id FROM chosen,target
WHERE drives.id=target.id AND drives.{side}_address_id IS NULL
RETURNING drives.id, chosen.id;
COMMIT;"""

def main():
    os.umask(0o077)
    directory = Path('/opt/teslamate-app')
    with open(directory / 'geocode.lock', 'w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        key = json.loads((directory / 'amap.json').read_text())['key']
        if not re.fullmatch(r'[0-9a-fA-F]{32}', key): raise GeocodeError('invalid_key')
        rows = json.loads(psql(QUERY, readonly=True))
        cache = {}
        filled = 0
        for endpoint in rows:
            point = (endpoint['latitude'], endpoint['longitude'])
            if point not in cache:
                cache[point] = reverse(key, *point)
                time.sleep(1)
            output = psql(fill_sql(endpoint, cache[point]))
            # pg_advisory_xact_lock produces an empty line; only UPDATE RETURNING counts.
            if any(re.fullmatch(r'\d+\|\d+', line) for line in output.splitlines()): filled += 1
        result = {'status': 'ok', 'pending_examined': len(rows), 'filled_endpoints': filled,
            'finished_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        (directory / 'last-geocode.json').write_text(json.dumps(result)+'\n')
        print(json.dumps(result))

if __name__ == '__main__':
    try: main()
    except GeocodeError as error:
        # GeocodeError is constructed only from fixed labels or validated numeric codes.
        print('Geocoding failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print('Geocoding failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
