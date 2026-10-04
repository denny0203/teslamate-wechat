#!/usr/bin/env python3
"""Create private configuration interactively. Secrets never enter CLI arguments."""
import getpass
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from configuration import legacy_key_role, validate_config, validate_url


def write_private(path, value):
    path = Path(path)
    # Refuse overwriting existing configurations or following symlinks.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(value)
    print('Configuration created; values not displayed.')


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parents[1]
    mode = sys.argv[1] if len(sys.argv) == 2 else ''
    if mode == 'client':
        url = validate_url(input('Supabase HTTPS project URL: ').strip())
        key = getpass.getpass('Legacy anon key (hidden): ').strip()
        if legacy_key_role(key) != 'anon':
            raise ValueError('Client requires legacy anon key; never service_role')
        write_private(root / 'miniprogram/config.js', 'module.exports = ' + json.dumps({'url': url, 'anonKey': key}) + ';\n')
    elif mode == 'backend':
        url = input('Supabase HTTPS project URL: ').strip()
        owner = input('Authentication user UUID (not email): ').strip()
        key = getpass.getpass('Legacy service_role key (hidden): ').strip()
        config = validate_config({'url': url, 'owner_id': owner, 'service_role_key': key}, require_key=True)
        write_private('/opt/teslamate-app/supabase.json', json.dumps(config, indent=2) + '\n')
    elif mode == 'amap':
        import re
        key = getpass.getpass('Amap Web Service key (hidden): ').strip()
        if not re.fullmatch(r'[0-9a-fA-F]{32}', key):
            raise ValueError('Expected Amap Web Service key')
        write_private('/opt/teslamate-app/amap.json', json.dumps({'key': key}) + '\n')
    else:
        raise ValueError('Usage: python3 tools/configure.py client|backend|amap')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Configuration failed: ' + type(error).__name__ + '; existing files are never overwritten.', file=sys.stderr)
        sys.exit(1)
