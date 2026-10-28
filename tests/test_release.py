"""Production trust boundaries, fail-closed scanning and release operations."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import struct
import threading
import tempfile
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet

from backend import malware
from backend.db import initialize, database
from backend.domain import DomainError
from backend.main import create_app
from backend.runtime import configuration_errors
from backend.worker import run_once
from scripts.release_preflight import read_environment, capacity_errors, compose_errors
from scripts.offsite_backup import pull_backup
from scripts.encrypted_backup import private_write, decrypt_backup
from scripts.monitor_release import inspect, write_metrics
from scripts.bootstrap_owner import bootstrap


@pytest.fixture
def scanner(tmp_path, monkeypatch):
    # Exercise the real socket framing and fragmented replies, not a patched
    # malware_screen. The separate container check uses the real ClamAV daemon.
    temporary = tempfile.TemporaryDirectory(prefix='doaide-scan-', dir='/tmp')
    path = Path(temporary.name) / 'clamd.sock'
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path)); listener.listen(); listener.settimeout(.1)
    state = {'reply': b'stream: OK\0', 'date': datetime.now(timezone.utc), 'content': [], 'stop': False, 'path': str(path)}
    def serve():
        while not state['stop']:
            try: client, _ = listener.accept()
            except socket.timeout: continue
            with client:
                client.settimeout(2)
                command = b''
                while not command.endswith(b'\0'): command += client.recv(1)
                if command == b'zVERSION\0':
                    reply = ('ClamAV/test/' + state['date'].strftime('%a %b %d %H:%M:%S %Y') + '\0').encode()
                else:
                    assert command == b'zINSTREAM\0'
                    def read(size):
                        data = b''
                        while len(data) < size: data += client.recv(size - len(data))
                        return data
                    content = b''
                    while size := struct.unpack('!I', read(4))[0]: content += read(size)
                    state['content'].append(content); reply = state['reply']
                try:
                    client.sendall(reply[:3]); client.sendall(reply[3:])
                except BrokenPipeError: pass
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    monkeypatch.setenv('DOAIDE_CLAMD_SOCKET', str(path))
    yield state
    state['stop'] = True; thread.join(timeout=3); listener.close(); temporary.cleanup()


def test_scanning_streams_exact_bytes_and_rejects_bad_or_stale_results(scanner):
    content = b'evidence' * 20000
    assert malware.scanner_ready() and malware.malware_screen(content) == 'clean'
    assert scanner['content'] == [content]
    for reply in (b'stream: Eicar-Test-Signature FOUND\0', b'INSTREAM size limit exceeded. ERROR\0', b'OK\0', b'stream: OK', b'x' * 4096):
        scanner['reply'] = reply
        with pytest.raises(DomainError): malware.malware_screen(content)
    scanner['reply'] = b'stream: OK\0'; scanner['date'] -= timedelta(days=4)
    assert not malware.scanner_ready()
    with pytest.raises(DomainError, match='definitions'): malware.malware_screen(content)


def test_missing_scanner_never_falls_back_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv('DOAIDE_CLAMD_SOCKET', str(tmp_path / 'absent.sock'))
    assert not malware.scanner_ready()
    with pytest.raises(DomainError): malware.malware_screen(b'anything')


def test_worker_sigterm_exits_cleanly_and_preserves_database(tmp_path):
    path = tmp_path / 'worker.db'
    env = {**os.environ, 'DOAIDE_DB_PATH': str(path), 'DOAIDE_ENVIRONMENT': 'development'}
    process = subprocess.Popen([sys.executable, '-m', 'backend.worker'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            if path.exists():
                try:
                    with database(path) as db:
                        if db.execute("SELECT last_seen FROM runtime_status WHERE name='worker'").fetchone():break
                except Exception:pass
            time.sleep(.1)
        else:raise AssertionError('Worker did not start')
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr.decode()
        with database(path) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        if process.poll() is None:process.kill();process.wait()


def production_env(tmp_path):
    return {'DOAIDE_ENVIRONMENT': 'production', 'DOAIDE_PUBLIC_URL': 'https://suite.example.test',
            'DOAIDE_DB_PATH': str(tmp_path / 'test.db'), 'DOAIDE_REQUIRE_WORKER': 'true',
            'DOAIDE_REQUIRE_MALWARE_SCAN': 'true', 'DOAIDE_CLAMD_SOCKET': str(tmp_path / 'clamd.sock'),
            'FORWARDED_ALLOW_IPS': '127.0.0.1,172.18.0.1'}


def test_production_origin_host_cookie_and_readiness(tmp_path, monkeypatch, scanner):
    env = production_env(tmp_path)
    env['DOAIDE_CLAMD_SOCKET'] = scanner['path']
    for key, value in env.items(): monkeypatch.setenv(key, value)
    bootstrap(env['DOAIDE_DB_PATH'], 'pilot@example.test', 'test-only-password-long')
    with pytest.raises(ValueError, match='already exists'):
        bootstrap(env['DOAIDE_DB_PATH'], 'pilot@example.test', 'replacement-password')
    with TestClient(create_app(), base_url='https://suite.example.test') as client:
        assert client.get('/api/ready').status_code == 503
        run_once()
        assert client.get('/api/ready').json() == {'ready': True}
        assert client.get('/api/health', headers={'Host': 'attacker.example'}).status_code == 400
        body = {'email': 'pilot@example.test', 'password': 'test-only-password-long'}
        assert client.post('/api/auth/register', json=body).status_code == 403
        assert client.post('/api/auth/login', json=body, headers={'Origin': 'http://localhost:5173'}).status_code == 403
        response = client.post('/api/auth/login', json=body, headers={'Origin': 'https://suite.example.test'})
        assert response.status_code == 200 and 'Secure' in response.headers['set-cookie']
        scanner['date'] -= timedelta(days=4)
        assert client.get('/api/ready').status_code == 503
        assert client.get('/api/diagnostics').json()['scanner_healthy'] is False


def test_configuration_rejects_untrusted_proxy_and_incomplete_runtime(tmp_path):
    env = production_env(tmp_path)
    assert configuration_errors(env) == []
    for value in ('*', '0.0.0.0/0', '::/0', ''):
        assert configuration_errors({**env, 'FORWARDED_ALLOW_IPS': value})
    for value in ('http://suite.example.test', 'https://user:secret@suite.example.test', 'https://suite.example.test/path'):
        assert configuration_errors({**env, 'DOAIDE_PUBLIC_URL': value})
    assert configuration_errors({**env, 'DOAIDE_REQUIRE_WORKER': 'false'})
    assert configuration_errors({**env, 'DOAIDE_REQUIRE_VERIFIED_EMAIL': 'true'})
    assert configuration_errors({**env, 'DOAIDE_REGISTRATION_MODE': 'open'})


def test_release_refuses_shared_secrets_mutable_images_and_host_pressure(tmp_path):
    env = tmp_path / 'production.env'; env.write_text('KEY=secret\n'); env.chmod(0o644)
    with pytest.raises(ValueError): read_environment(env)
    env.chmod(0o600); assert read_environment(env) == {'KEY': 'secret'}
    env.write_text('KEY=first\nKEY=second\n')
    with pytest.raises(ValueError): read_environment(env)
    state = {'disk_percent': 82, 'disk_available_gib': 6.74, 'memory_available_gib': 1.43, 'swap_percent': 98.9}
    assert len(capacity_errors(state)) == 3
    assert capacity_errors({'disk_percent': 40, 'disk_available_gib': 25, 'memory_available_gib': 7, 'swap_percent': 10}) == []
    assert any('SHA256' in error for error in compose_errors({'services': {'app': {'image': 'app:latest'}}}))


def test_offsite_backup_restores_and_monitor_rejects_stale_receipts(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'; initialize(source)
    key = tmp_path / 'key'; private_write(key, Fernet.generate_key())
    def transfer(args, stdout, **kwargs):
        assert 'StrictHostKeyChecking=yes' in args and 'exec -T app' in args[-1]
        stdout.write(source.read_bytes()); return SimpleNamespace(returncode=0)
    monkeypatch.setattr('scripts.offsite_backup.subprocess.run', transfer)
    destination = tmp_path / 'offsite' / 'test.enc'
    receipt = pull_backup('backup-source', '/opt/doaide-suite', 'doaide-suite', key, destination)
    assert receipt['offsite_verified'] and receipt['restore_integrity'] == 'ok'
    restored = tmp_path / 'restored.db'; decrypt_backup(destination, restored, key)
    with database(restored) as db: assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with pytest.raises(ValueError): pull_backup('backup-source', '/opt/doaide-suite', 'doaide-suite', key, destination)
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"ready":true}'
    monkeypatch.setattr('urllib.request.OpenerDirector.open', lambda *a, **k: Response())
    result = inspect('https://suite.example.test', destination.parent)
    assert result['healthy']
    receipt['verified_at'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    destination.with_suffix('.enc.receipt.json').write_text(json.dumps(receipt))
    result = inspect('https://suite.example.test', destination.parent)
    assert not result['healthy']
    metrics = tmp_path / 'suite.prom'; write_metrics(metrics, result)
    assert 'doaide_suite_healthy 0\n' in metrics.read_text()
    destination.unlink()
    assert not inspect('https://suite.example.test', destination.parent)['healthy']
