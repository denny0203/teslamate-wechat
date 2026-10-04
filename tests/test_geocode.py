import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('geocode', Path(__file__).parents[1] / 'backend/geocode_drives.py')
geo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)

class GeocodeTests(unittest.TestCase):
    def test_gps_conversion_precedes_lookup_and_handles_empty_city(self):
        calls = []
        def request(key, path, params):
            calls.append((path, params))
            if path.endswith('/convert'): return {'locations': '116.406,39.908'}
            return {'regeocode': {'formatted_address': '北京市测试路1号', 'addressComponent':
                {'city': [], 'province': '北京市', 'district': '测试区', 'streetNumber': {'street': '测试路', 'number': '1号'}}}}
        attrs = geo.reverse('test', 39.9, 116.4, request)
        self.assertEqual(calls[0][1], {'locations': '116.400000,39.900000', 'coordsys': 'gps'})
        self.assertEqual(calls[1][1]['location'], '116.406000,39.908000')
        self.assertEqual(attrs['latitude'], 39.9)  # Stored GPS stays original.
        self.assertEqual(attrs['city'], '北京市')
        self.assertNotIn('key', attrs['raw'])

    def test_invalid_coordinates_never_send(self):
        def forbidden(*args): self.fail('Must not transmit invalid coordinates')
        for point in [(float('nan'), 116), (91, 116), (30, float('inf'))]:
            with self.assertRaises(geo.GeocodeError): geo.reverse('test', *point, forbidden)

    def test_empty_address_not_written(self):
        def request(key, path, params):
            return {'locations': '116.4,39.9'} if path.endswith('/convert') else {'regeocode': {'formatted_address': []}}
        with self.assertRaises(geo.GeocodeError): geo.reverse('test', 39.9, 116.4, request)

    def test_sql_preserves_existing_links_and_compares_position(self):
        attrs = {'display_name': "测试'O路", 'latitude': 30.0, 'longitude': 120.0,
            'road': '', 'house_number': '', 'city': '', 'county': '', 'state': '', 'country': '', 'raw': {'provider': geo.PROVIDER}}
        query = geo.fill_sql({'id': 1, 'position_id': 2, 'side': 'start', 'latitude': 30, 'longitude': 120}, attrs)
        self.assertIn('start_address_id IS NULL', query)
        self.assertIn('start_position_id=2', query)
        self.assertIn('FOR UPDATE', query)
        self.assertIn("测试''O路", query)
        self.assertNotIn('UPDATE positions', query)
        with self.assertRaises(ValueError): geo.fill_sql({'id': 1, 'position_id': 2, 'side': 'invalid', 'latitude': 30, 'longitude': 120}, attrs)

if __name__ == '__main__': unittest.main()
