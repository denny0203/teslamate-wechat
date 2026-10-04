"""Offline pre-publication check; prints paths/rule names, never matched values.
Heuristic only: complements human review, not a complete secret detector.
Run before staging and after creating local deployment configurations.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    'legacy_jwt': re.compile(r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github_token': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'supabase_secret': re.compile(r'sb_secret_[A-Za-z0-9_-]{20,}'),
    'aliyun_access_key': re.compile(r'LTAI[A-Za-z0-9]{16,}'),
    'wechat_app_id': re.compile(r'wx[0-9a-f]{16}'),
    'cloud_project_id': re.compile(r'spb-[a-z0-9]{10,}'),
    'personal_absolute_path': re.compile(r'/' + r'Users/[^/\s]+/'),
    'email_address': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    'ipv4_literal': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
}
ALLOWED_IPS = {'127.0.0.1','0.0.0.0'}
PRIVATE_NAMES = {'config.js', 'project.private.config.json', 'supabase.json', 'amap.json', '.env', '.DS_Store'}


def main():
    paths = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts]
    # Git ignore rules also work before git init via --no-index + an explicit exclude file.
    result = subprocess.run(['git','-c','core.excludesFile='+str(ROOT/'.gitignore'),
                             'check-ignore','--no-index','--stdin'],cwd=ROOT,
                            input='\n'.join(paths)+'\n',text=True,capture_output=True)
    # Without a repository Git may refuse check-ignore. Use a conservative local filter then.
    ignored = set(result.stdout.splitlines()) if result.returncode in (0,1) else set()
    failed = []
    checked = 0
    for relative in paths:
        p = ROOT / relative
        parts = Path(relative).parts
        private = p.name in PRIVATE_NAMES or p.suffix in ('.pyc','.csv','.bck','.dump','.pem','.key') or any(x in parts for x in ('.private','__pycache__','backups','preview','release','node_modules'))
        if relative in ignored or private:
            # Private files must remain untracked if a repository exists.
            tracked = subprocess.run(['git','ls-files','--error-unmatch','--',relative],cwd=ROOT,capture_output=True)
            if tracked.returncode == 0:failed.append((relative,'tracked_private_file'))
            continue
        if p.suffix == '.png':continue  # Only generated artwork is included; provenance in THIRD_PARTY.md.
        try:content = p.read_text()
        except UnicodeError:
            failed.append((relative,'unexpected_binary'));continue
        checked += 1
        for name, pattern in RULES.items():
            matches = pattern.findall(content)
            if name == 'ipv4_literal':matches = [v for v in matches if v not in ALLOWED_IPS]
            if matches:failed.append((relative,name))
    for relative, name in failed:print(relative + ': ' + name)
    print('Public text files checked: ' + str(checked) + '; findings: ' + str(len(failed)))
    return bool(failed)


if __name__ == '__main__':sys.exit(main())
