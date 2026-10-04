import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from configuration import validate_config, validate_url, legacy_key_role
from sync_details import sync


class ConfigurationTests(unittest.TestCase):
    def test_arbitrary_project_and_uuid_supported(self):
        config = validate_config({'url': 'https://another.example.com/',
                                  'owner_id': '00000000-0000-0000-0000-000000000001'})
        self.assertEqual(config['url'], 'https://another.example.com')

    def test_unsafe_destination_rejected(self):
        for url in ['http://example.com', 'https://user:pass@' + 'example.com',
                    'https://example.com/path', 'https://example.com?key=value',
                    'https://example.com#fragment', 'https://example.com:8000', None]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_client_or_new_format_key_rejected_for_backend(self):
        import base64
        anon = 'test.' + base64.urlsafe_b64encode(json.dumps({'role': 'anon'}).encode()).decode().rstrip('=') + '.test'
        self.assertEqual(legacy_key_role(anon), 'anon')
        for key in [anon, 'placeholder', 'sb_secret_placeholder']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config({'url': 'https://example.invalid',
                                 'owner_id': '00000000-0000-0000-0000-000000000001',
                                 'service_role_key': key}, require_key=True)

    def test_destination_change_republishes_same_owner_details(self):
        config = {'url': 'https://first.example.com', 'owner_id': '00000000-0000-0000-0000-000000000001'}
        row = {'id': 1, 'car_id': 1, 'started_at': '2026-01-01T00:00:00Z',
               'ended_at': '2026-01-01T00:10:00Z', 'distance_km': 5, 'positions': []}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = lambda query: [row]
            publish = lambda *args: None
            self.assertEqual(sync(config, directory, source, publish)['published'], 1)
            self.assertEqual(sync(config, directory, source, publish)['published'], 0)
            config['url'] = 'https://second.example.com'
            self.assertEqual(sync(config, directory, source, publish)['published'], 1)
