"""Exercise the release Compose file with isolated volumes and real ClamAV.

No browser, production database or provider account is accessed. FreshClam
downloads public signatures. The harmless EICAR fixture proves rejection.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.catalog import CATALOG
from scripts.release_preflight import preflight

ROOT = Path(__file__).resolve().parents[1]


def check(app_image, worker_image, scanner_image):
    project = 'suite-check-' + uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        root = Path(directory)
        environment = root / 'production.env'
        environment.write_text((ROOT / 'deploy/production.env.example').read_text().replace('suite.example.com', 'suite.example.test'))
        environment.chmod(0o600)
        release = root / 'release.env'
        images = {}
        for key, image in [('DOAIDE_IMAGE', app_image), ('DOAIDE_WORKER_IMAGE', worker_image), ('DOAIDE_SCANNER_IMAGE', scanner_image)]:
            images[key] = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip()
        release.write_text('\n'.join(f'{key}={value}' for key, value in images.items()) + '\nDOAIDE_PORT=0\n')
        release.chmod(0o600)
        report = preflight(environment, release, ROOT / 'compose.production.yml', False)
        if not report['ready']: raise AssertionError(report)
        process_env = {**os.environ, **images, 'DOAIDE_ENV_FILE': str(environment), 'DOAIDE_PORT': '0'}
        compose = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'compose.production.yml')]
        def run(*args, timeout=60):
            return subprocess.check_output(compose + list(args), env=process_env, text=True, timeout=timeout).strip()
        try:
            run('up', '-d', '--wait', '--wait-timeout', '300', timeout=360)
            address = run('port', 'app', '8012')
            with httpx.Client(base_url='http://' + address, timeout=15) as client:
                assert client.get('/api/ready').json() == {'ready': True}
                credentials = {'email': 'stack@example.test', 'password': 'synthetic-stack-password'}
                assert client.post('/api/auth/register', json=credentials).status_code == 403
                run('exec', '-T', 'app', 'python', '-c', "import os; from scripts.bootstrap_owner import bootstrap; bootstrap(os.environ['DOAIDE_DB_PATH'], 'stack@example.test', 'synthetic-stack-password')")
                created = client.post('/api/auth/login', json=credentials)
                assert created.status_code == 200, created.text
                assert 'Secure' in created.headers['set-cookie']
                # HTTP loopback is used only for this API test. Explicitly replay
                # the secure cookie; production browsers use the HTTPS proxy.
                client.headers['Cookie'] = 'doaide_session=' + created.cookies['doaide_session']
                record = client.post('/api/products/scope/records', json={'title': 'Release test', 'payload': CATALOG['scope']['sample']}).json()
                endpoint = '/api/records/' + record['id'] + '/files'
                clean = client.post(endpoint, files={'file': ('scope.txt', b'Clean synthetic scope evidence', 'text/plain')})
                assert clean.status_code == 201, clean.text
                # EICAR is a standard harmless scanner test string, not malware.
                eicar = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
                rejected = client.post(endpoint, files={'file': ('eicar.txt', eicar, 'text/plain')})
                assert rejected.status_code == 422 and 'rejected' in rejected.text, rejected.text
                assert client.get('/api/health', headers={'Host': 'untrusted.example'}).status_code == 400
                run('stop', 'worker', timeout=130)
                run('exec', '-T', 'app', 'python', '-c', "from backend.db import database;\nwith database() as db: db.execute(\"UPDATE runtime_status SET last_seen='2000-01-01T00:00:00+00:00' WHERE name='worker'\")")
                assert client.get('/api/ready').status_code == 503
                run('start', 'worker')
                for _ in range(20):
                    if client.get('/api/ready').status_code == 200: break
                    time.sleep(.5)
                else: raise AssertionError('Worker restart did not restore readiness')
                assert client.get('/api/reports/portfolio').json()['total_records'] == 1
                # A stopped scanner must remove readiness and block persistence.
                run('stop', 'scanner')
                assert client.get('/api/ready').status_code == 503
                assert client.post(endpoint, files={'file': ('blocked.txt', b'Evidence', 'text/plain')}).status_code == 422
                workflow = client.get('/api/records/' + record['id'] + '/operations').json()
                assert len(workflow['files']) == 1
                backup = json.loads(run('exec', '-T', 'app', 'python', 'scripts/backup.py', '--output', '/tmp/rehearsal.db'))
                assert backup['integrity'] == backup['isolated_restore'] == 'ok'
                return {'images': images, 'fresh_compose_start': 'passed', 'worker_restart': 'passed',
                        'closed_registration_and_owner_login': 'passed', 'secure_cookie': 'passed', 'host_validation': 'passed', 'clean_upload': 'passed',
                        'real_clamav_eicar_rejection': 'passed', 'scanner_outage_fails_closed': 'passed',
                        'backup_restore': backup, 'production_data_touched': False, 'external_provider_requests': 0}
        except Exception:
            # All data/environment in this stack is synthetic; diagnostics are
            # safe to retain. Never use this helper against a production stack.
            print(run('logs', '--no-color', '--tail', '60'), file=sys.stderr)
            raise
        finally:
            run('down', '-v', '--remove-orphans', timeout=120)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='doaide-suite:release-validation')
    parser.add_argument('--worker', default='doaide-suite-worker:release-validation')
    parser.add_argument('--scanner', default='doaide-suite-scanner:release-validation')
    args = parser.parse_args()
    print(json.dumps(check(args.app, args.worker, args.scanner), indent=2))
