"""Pure detail processing. Never infer a route across missing samples.

WGS84 -> GCJ02 formulas adapted from wandergis/coordtransform (MIT),
see licenses/coordtransform-MIT.txt. Conversion is a display approximation;
verify alignment with provider-converted endpoints before device acceptance.
"""
import datetime as dt
import math
import re

GAP_SECONDS = 120
MAX_SPEED_KMH = 200
MIN_JUMP_INTERVAL_SECONDS = 5
SIMPLIFY_METRES = 10
PROCESSOR_VERSION = 'detail-v1.2-gcj02-rdp10-gap120-jump200-floor5-energy-rated'


def number(value, minimum=None, maximum=None):
    try:
        value = float(value) if value is not None else None
    except (ValueError, TypeError):
        return None
    if value is None or not math.isfinite(value):
        return None
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        return None
    return value


def coordinate(point):
    if not isinstance(point, dict):
        return None
    lat = number(point.get('latitude'), -90, 90)
    lon = number(point.get('longitude'), -180, 180)
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    return {'latitude': lat, 'longitude': lon}


def timestamp(value):
    try:
        normal = value.replace('Z', '+00:00')
        normal = re.sub(r'\.(\d+)(?=(?:[+-]\d{2}:\d{2})?$)', lambda m: '.'+m.group(1)[:6].ljust(6,'0'), normal)
        result = dt.datetime.fromisoformat(normal)
        return result if result.tzinfo else result.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def to_gcj(point):
    lat, lon = point['latitude'], point['longitude']
    if not (73.66 < lon < 135.05 and 3.86 < lat < 53.55):
        return dict(point)
    x, y = lon - 105, lat - 35
    a, ee = 6378245., .00669342162296594323
    dlat = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
    dlat += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    dlat += (20*math.sin(y*math.pi) + 40*math.sin(y/3*math.pi))*2/3
    dlat += (160*math.sin(y/12*math.pi) + 320*math.sin(y*math.pi/30))*2/3
    dlon = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
    dlon += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    dlon += (20*math.sin(x*math.pi) + 40*math.sin(x/3*math.pi))*2/3
    dlon += (150*math.sin(x/12*math.pi) + 300*math.sin(x/30*math.pi))*2/3
    rad = math.radians(lat)
    magic = 1 - ee*math.sin(rad)**2
    dlat = dlat*180 / ((a*(1-ee))/(magic*math.sqrt(magic))*math.pi)
    dlon = dlon*180 / (a/math.sqrt(magic)*math.cos(rad)*math.pi)
    return {'latitude': round(lat+dlat, 6), 'longitude': round(lon+dlon, 6)}


def distance(a, b):
    lat1, lat2 = math.radians(a['latitude']), math.radians(b['latitude'])
    dlat = lat2-lat1
    dlon = math.radians(b['longitude']-a['longitude'])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8*2*math.asin(math.sqrt(min(1, max(0, h))))


def line_distance(point, first, last):
    # Local equirectangular projection, sufficient for 10 m simplification.
    factor = math.cos(math.radians((first['latitude']+last['latitude'])/2))
    def xy(p):
        return (math.radians(p['longitude']-first['longitude'])*6371008.8*factor,
                math.radians(p['latitude']-first['latitude'])*6371008.8)
    px, py = xy(point)
    bx, by = xy(last)
    denom = bx*bx+by*by
    t = min(1, max(0, (px*bx+py*by)/denom)) if denom else 0
    return math.hypot(px-t*bx, py-t*by)


def simplify(points, tolerance=SIMPLIFY_METRES):
    if len(points) < 3:
        return points
    # Iterative RDP avoids stack overflow on long/zigzag routes.
    keep = {0, len(points)-1}
    stack = [(0, len(points)-1)]
    while stack:
        first, last = stack.pop()
        farthest, offset = 0, None
        for i in range(first+1, last):
            d = line_distance(points[i], points[first], points[last])
            if d > farthest:
                farthest, offset = d, i
        if farthest > tolerance:
            keep.add(offset)
            stack.extend([(first, offset), (offset, last)])
    return [points[i] for i in sorted(keep)]


def route(positions):
    segments, current = [], []
    invalid = duplicates = gaps = jumps = 0
    previous = None
    valid_count = 0
    for raw in positions:
        point, stamp = coordinate(raw), timestamp(raw.get('date'))
        if not point or not stamp:
            invalid += 1
            if current:
                segments.append(current)
                current = []
            previous = None
            continue
        valid_count += 1
        if previous:
            seconds = (stamp-previous[1]).total_seconds()
            metres = distance(previous[0], point)
            if seconds == 0 and metres < .1:
                duplicates += 1
                continue
            is_gap = seconds > GAP_SECONDS
            # Position receipt timestamps are not guaranteed GPS fix timestamps.
            # Sub-second updates must not turn an ordinary 20 m movement into
            # a purported 200+ km/h jump. This is an anomaly heuristic, not speed.
            is_jump = seconds < 0 or metres/max(seconds, MIN_JUMP_INTERVAL_SECONDS)*3.6 > MAX_SPEED_KMH
            if is_gap or is_jump:
                gaps += int(is_gap)
                jumps += int(is_jump)
                if current:
                    segments.append(current)
                current = []
        current.append(to_gcj(point))
        previous = (point, stamp)
    if current:
        segments.append(current)
    display = [simplify(s) for s in segments]
    return display, {'raw_points': len(positions), 'valid_points': valid_count,
        'display_points': sum(map(len, display)), 'segments': len(display),
        'filtered_points': invalid, 'duplicate_points': duplicates,
        'gaps': gaps, 'jumps': jumps, 'has_gaps': bool(gaps),
        'has_anomalies': bool(jumps or invalid),
        'jump_interval_floor_seconds': MIN_JUMP_INTERVAL_SECONDS,
        'simplification_metres': SIMPLIFY_METRES}


def build_detail(row):
    fields = ['id', 'car_id', 'started_at', 'ended_at', 'start_address', 'end_address']
    summary = {k: row.get(k) for k in fields}
    for key in ['distance_km', 'speed_max', 'start_range_km', 'end_range_km']:
        summary[key] = number(row.get(key), 0)
    for key in ['start_battery', 'end_battery']:
        summary[key] = number(row.get(key), 0, 100)
    for key in ['inside_temp_avg', 'outside_temp_avg']:
        summary[key] = number(row.get(key))
    # Same rated-range consumption formula as TeslaMate's Drives dashboard.
    # This is an estimate, not a direct vehicle energy meter reading.
    efficiency = number(row.get('car_efficiency'), 0)
    start_range, end_range = summary['start_range_km'], summary['end_range_km']
    energy = None
    if row.get('ended_at') and efficiency and start_range is not None and end_range is not None and start_range >= end_range:
        energy = (start_range - end_range) * efficiency
    distance = summary['distance_km']
    summary['energy_used_kwh'] = energy
    summary['average_consumption_wh_km'] = energy / distance * 1000 if energy is not None and distance and distance > 0 else None
    summary['energy_method'] = 'teslamate-rated-range' if energy is not None else None
    segments, quality = route(row.get('positions') or [])
    start, end = timestamp(row.get('started_at')), timestamp(row.get('ended_at'))
    unfinished = not row.get('ended_at')
    seconds = (end-start).total_seconds() if start and end else None
    summary['duration_seconds'] = seconds if seconds is not None and seconds >= 0 else None
    summary['duration_invalid'] = bool(row.get('ended_at') and (seconds is None or seconds < 0))
    summary['average_speed'] = summary['distance_km']/seconds*3600 if seconds and seconds > 0 and summary['distance_km'] is not None else None
    endpoints = {}
    for side in ['start', 'end']:
        point = coordinate(row.get(side+'_point'))
        if point:
            endpoints[side] = to_gcj(point)
    status = 'unfinished' if unfinished else 'ready' if quality['valid_points'] else 'empty'
    # Do not expose a partial live route for an ongoing drive.
    if unfinished:
        segments, endpoints = [], {}
    return {'summary': summary, 'coordinate_system': 'gcj02',
        'processor_version': PROCESSOR_VERSION, 'segments': segments,
        'endpoints': endpoints, 'quality': quality, 'status': status}
