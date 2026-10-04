"""Validate user-supplied destinations; never log configuration values."""
import base64
import json
import uuid
from urllib.parse import urlsplit


def legacy_key_role(key):
    """Decode metadata only, not signature verification; server verifies the JWT."""
    try:
        part = key.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))['role']
    except (AttributeError, IndexError, ValueError, KeyError, UnicodeError):
        raise ValueError('Expected a legacy Supabase JWT key') from None


def validate_url(url):
    if not isinstance(url, str):
        raise ValueError('Expected HTTPS project URL')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port not in (None, 443)):
        raise ValueError('Expected HTTPS project origin without path or credentials')
    return url.rstrip('/')


def validate_config(config, require_key=False):
    result = dict(config)
    result['url'] = validate_url(result.get('url'))
    result['owner_id'] = str(uuid.UUID(result['owner_id']))
    if require_key and legacy_key_role(result.get('service_role_key', '')) != 'service_role':
        raise ValueError('Backend requires the legacy service_role key')
    return result
