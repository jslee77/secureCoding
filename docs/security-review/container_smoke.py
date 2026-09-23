"""docker build -t securedocs:test . 후 실행. 임시 컨테이너·tmpfs만 사용한다."""
import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()

for seed in ('0', '1'):
    name = 'securedocs-review-' + uuid.uuid4().hex[:10]
    started = False
    try:
        docker('run', '--rm', '-d', '--name', name, '--tmpfs',
               '/app/instance:rw,uid=10001,gid=10001,mode=0700',
               '-p', '127.0.0.1::5000', '-e', 'SEED_DEMO_DATA=' + seed, 'securedocs:test')
        started = True
        port = docker('port', name, '5000/tcp').split(':')[-1]
        base = 'http://127.0.0.1:' + port
        for attempt in range(60):
            try:
                with urllib.request.urlopen(base, timeout=1) as r:
                    assert r.status == 200
                    assert "script-src 'self'" in r.headers['Content-Security-Policy']
                break
            except (OSError, urllib.error.URLError):
                time.sleep(.5)
        else:
            raise RuntimeError('health timeout')
        uid = docker('exec', name, 'id', '-u')
        assert uid == '10001'
        docker('exec', name, 'python', '-c',
               "from pathlib import Path; assert not list(Path('/app').glob('.env*')); assert not Path('/app/.venv').exists()")
        req = urllib.request.Request(base + '/api/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
            headers={'Content-Type':'application/json', 'X-Requested-With':'SecureDocs'})
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            assert response.status == (200 if seed == '1' else 401)
            assert 'no-store' in response.headers['Cache-Control']
        print(f'SEED_DEMO_DATA={seed}: gunicorn HTTP/CSP/login/no-store OK, uid={uid}, image excludes .env/.venv', flush=True)
    finally:
        if started:
            docker('stop', name)
print('Temporary containers removed; existing Compose service and volumes untouched.')
