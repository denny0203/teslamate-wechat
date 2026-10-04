import copy
import datetime as dt
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from drive_details import build_detail, route, simplify, line_distance, to_gcj
from sync_details import sync
PROJECT_URL = 'https://example.invalid'


def position(seconds,lat=30.,lon=120.,ident=1):
    return {'id':ident,'date':(dt.datetime(2026,10,2,tzinfo=dt.timezone.utc)+dt.timedelta(seconds=seconds)).isoformat(),
        'latitude':lat,'longitude':lon}


def drive(ident=1):
    return {'id':ident,'car_id':1,'started_at':'2026-10-01T15:59:00Z','ended_at':'2026-10-01T16:01:00Z',
        'distance_km':1.1,'speed_max':0,'inside_temp_avg':0,'outside_temp_avg':-5,
        'start_battery':0,'end_battery':None,'start_range_km':100,'end_range_km':101,
        'start_point':{'latitude':30,'longitude':120},'end_point':{'latitude':30,'longitude':120.001},
        'positions':[position(0),position(60,lon=120.001)]}


class DetailsTest(unittest.TestCase):
    def test_zero_is_valid_missing_is_not_zero(self):
        p=build_detail(drive())
        self.assertEqual(p['summary']['start_battery'],0)
        self.assertIsNone(p['summary']['end_battery'])
        self.assertEqual(p['summary']['inside_temp_avg'],0)
        self.assertEqual(p['summary']['outside_temp_avg'],-5)
        self.assertEqual(p['summary']['average_speed'],33)
        self.assertEqual(p['summary']['duration_seconds'],120)

    def test_no_guessed_route_and_unfinished_hides_live_positions(self):
        row=drive();row['positions']=[]
        self.assertEqual(build_detail(row)['status'],'empty')
        row['positions']=[position(0)]
        result=build_detail(row)
        self.assertEqual(len(result['segments'][0]),1)
        row['ended_at']=None
        result=build_detail(row)
        self.assertEqual(result['status'],'unfinished')
        self.assertEqual(result['segments'],[])
        self.assertEqual(result['endpoints'],{})

    def test_gaps_jumps_invalids_duplicates_do_not_create_bridges(self):
        points=[position(0),position(0),position(10,lon=120.001),position(200,lon=120.002),
            position(210,lon=121),position(220,lat=float('nan')),position(230,lon=121.001)]
        segments,q=route(points)
        self.assertEqual([len(s) for s in segments],[2,1,1,1])
        self.assertEqual(q['gaps'],1)
        self.assertEqual(q['jumps'],1)
        self.assertEqual(q['filtered_points'],1)
        self.assertEqual(q['duplicate_points'],1)
        self.assertTrue(q['has_gaps'])

    def test_invalid_duration_and_nonfinite_summary(self):
        row=drive();row['ended_at']='2026-10-01T15:58:00Z';row['distance_km']=float('inf');row['start_battery']=101
        p=build_detail(row)
        self.assertTrue(p['summary']['duration_invalid'])
        self.assertIsNone(p['summary']['distance_km'])
        self.assertIsNone(p['summary']['start_battery'])
        self.assertIsNone(p['summary']['average_speed'])
        json.dumps(p,allow_nan=False)

    def test_subsecond_updates_keep_route_but_large_jump_is_broken(self):
        points=[position(0),position(.1,lon=120.0002),position(.2,lon=120.0004),
                position(.2,lon=120.0006),position(.3,lon=121)]
        segments,q=route(points)
        self.assertEqual(q['jumps'],1)
        self.assertEqual(q['gaps'],0)
        self.assertFalse(q['has_gaps'])
        self.assertTrue(q['has_anomalies'])
        self.assertEqual(len(segments),2)
        self.assertEqual(segments[0][0],to_gcj(points[0]))
        self.assertEqual(segments[0][-1],to_gcj(points[3]))

    def test_closed_loop_keeps_turns_and_simplification_error(self):
        points=[{'latitude':30+math.sin(i/10)*.001,'longitude':120+math.cos(i/10)*.001} for i in range(64)]
        reduced=simplify(points)
        self.assertEqual(reduced[0],points[0]);self.assertEqual(reduced[-1],points[-1])
        self.assertGreater(len(reduced),8)
        indices=[points.index(p) for p in reduced]
        for a,b in zip(indices,indices[1:]):
            self.assertTrue(all(line_distance(p,points[a],points[b])<=10 for p in points[a:b+1]))

    def test_conversion_known_reference_and_foreign_identity(self):
        # Fixed reference from coordtransform WGS84->GCJ02, not this implementation.
        p=to_gcj({'latitude':39.915,'longitude':116.404})
        self.assertAlmostEqual(p['longitude'],116.41024449916938,places=5)
        self.assertAlmostEqual(p['latitude'],39.91640428150164,places=5)
        foreign={'latitude':51.5,'longitude':-.1}
        self.assertEqual(to_gcj(foreign),foreign)

    def test_sync_atomic_publication_idempotency_change_and_backlog(self):
        rows=[drive(i) for i in range(1,8)]
        config={'url':PROJECT_URL,'owner_id':'00000000-0000-0000-0000-000000000001'}
        calls=[]
        with tempfile.TemporaryDirectory() as temp:
            pub=lambda c,t,r,k:calls.append((t,copy.deepcopy(r)))
            first=sync(config,Path(temp),lambda q:rows,pub)
            self.assertEqual(first['published'],5);self.assertEqual(first['remaining'],2)
            self.assertEqual(sum(t=='app_drive_details' for t,r in calls),5)
            for t,r in calls:
                if t=='app_drive_details':self.assertTrue(r[0]['payload']['segments'])
            self.assertEqual(sync(config,Path(temp),lambda q:rows,pub)['published'],2)
            self.assertEqual(sync(config,Path(temp),lambda q:rows,pub)['published'],0)
            rows[0]['positions'][0]['longitude']=120.0001
            self.assertEqual(sync(config,Path(temp),lambda q:rows,pub)['published'],1)

    def test_failed_snapshot_is_not_marked_published(self):
        config={'url':PROJECT_URL,'owner_id':'00000000-0000-0000-0000-000000000001'}
        with tempfile.TemporaryDirectory() as temp:
            def fail(c,t,r,k):
                if t=='app_drive_details':raise RuntimeError('test failure')
            with self.assertRaises(RuntimeError):sync(config,Path(temp),lambda q:[drive()],fail)
            calls=[]
            sync(config,Path(temp),lambda q:[drive()],lambda c,t,r,k:calls.append(t))
            self.assertIn('app_drive_details',calls)

    def test_long_unfinished_drive_remains_in_next_source_query(self):
        config={'url':PROJECT_URL,'owner_id':'00000000-0000-0000-0000-000000000001'}
        row=drive(22);row['ended_at']=None
        with tempfile.TemporaryDirectory() as temp:
            sync(config,Path(temp),lambda q:[row],lambda *args:None)
            queries=[]
            sync(config,Path(temp),lambda q:queries.append(q) or [row],lambda *args:None)
            self.assertIn('d.id IN (22)',queries[0])

class TimestampCompatibilityTest(unittest.TestCase):
    def test_postgres_fractional_seconds_on_python39(self):
        from drive_details import timestamp
        self.assertEqual(timestamp('2026-10-02 00:00:00.07').microsecond,70000)
        self.assertEqual(timestamp('2026-10-02T00:00:00.7Z').microsecond,700000)

class EnergyTests(unittest.TestCase):
    def test_teslamate_estimate_uses_unrounded_range_and_distance(self):
        row={'ended_at':'2026-10-04T00:10:00Z','distance_km':4.5,
             'start_range_km':330.2,'end_range_km':324.4,'car_efficiency':0.1377}
        summary=build_detail(row)['summary']
        self.assertAlmostEqual(summary['energy_used_kwh'],0.79866)
        self.assertAlmostEqual(summary['average_consumption_wh_km'],177.48)
        self.assertEqual(summary['energy_method'],'teslamate-rated-range')

    def test_missing_increased_range_zero_distance_and_zero_energy(self):
        base={'ended_at':'2026-10-04T00:10:00Z','distance_km':4.5,'start_range_km':330,'end_range_km':324,'car_efficiency':0.1377}
        for changes in [{'car_efficiency':None},{'car_efficiency':0},{'end_range_km':340},{'start_range_km':None},{'ended_at':None}]:
            self.assertIsNone(build_detail(dict(base,**changes))['summary']['energy_used_kwh'])
        summary=build_detail(dict(base,distance_km=0))['summary']
        self.assertIsNotNone(summary['energy_used_kwh']);self.assertIsNone(summary['average_consumption_wh_km'])
        summary=build_detail(dict(base,end_range_km=330))['summary']
        self.assertEqual(summary['energy_used_kwh'],0);self.assertEqual(summary['average_consumption_wh_km'],0)

if __name__=='__main__':unittest.main()
