"""Read-only uptime/capacity probe for systemd or an external monitoring host.

No alert is sent by this tool. Nonzero exit and Prometheus textfile gauges can
feed the operator's existing alert routing without transmitting business data.
"""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import urllib.request
import sys
if __package__:
    from .release_preflight import capacity
else:
    from release_preflight import capacity


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def inspect(url, backup_directory=None, host=False):
    origin = urlsplit(url)
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('Monitor requires a bare HTTPS origin')
    errors = []
    try:
        with urllib.request.build_opener(NoRedirect).open(url.rstrip('/') + '/api/ready', timeout=10) as response:
            if response.status != 200 or json.loads(response.read(1024)) != {'ready': True}:
                raise ValueError
    except Exception:
        errors.append('HTTPS readiness or certificate check failed')
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'errors': errors}
    if host:
        state = capacity()
        result['host'] = state
        if state['disk_percent'] >= 80:
            errors.append('Disk usage is at or above 80%')
        if state.get('swap_percent') is None or state['swap_percent'] >= 80:
            errors.append('Swap is missing or at or above 80%')
        if state.get('memory_available_gib', 0) < .5:
            errors.append('Available memory is below 512 MiB')
    if backup_directory:
        manifests = list(Path(backup_directory).glob('*.receipt.json'))
        try:
            latest = max(manifests, key=lambda p: p.stat().st_mtime)
            receipt = json.loads(latest.read_text())
            encrypted = latest.with_name(latest.name.removesuffix('.receipt.json'))
            if encrypted.is_symlink() or encrypted.stat().st_size != receipt['encrypted_bytes']:
                raise ValueError
            digest = hashlib.sha256()
            with encrypted.open('rb') as backup:
                while chunk := backup.read(1024 * 1024):digest.update(chunk)
            if digest.hexdigest() != receipt['sha256']:raise ValueError
            stamp = datetime.fromisoformat(receipt['verified_at'])
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            if not 0 <= age < 26 * 3600 or not receipt['offsite_verified'] or receipt['restore_integrity'] != 'ok':
                raise ValueError
            result['backup_age_seconds'] = int(age)
        except (ValueError, OSError, KeyError, TypeError):
            errors.append('No verified off-site backup receipt within 26 hours')
    result['healthy'] = not errors
    return result


def write_metrics(path, result):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as output:
        output.write('# HELP doaide_suite_healthy All configured release probes pass.\n# TYPE doaide_suite_healthy gauge\n')
        output.write(f'doaide_suite_healthy {int(result["healthy"])}\n')
        output.write(f'doaide_suite_probe_timestamp_seconds {int(datetime.now(timezone.utc).timestamp())}\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(output.name, destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--backup-directory')
    parser.add_argument('--host', action='store_true')
    parser.add_argument('--metrics')
    args = parser.parse_args()
    result = inspect(args.url, args.backup_directory, args.host)
    if args.metrics:
        write_metrics(args.metrics, result)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['healthy'] else 1)
