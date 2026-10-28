"""Read-only host/release gate. Reports configuration names, never their values.

Run on the target host with Docker Compose installed, before pulling images or
changing traffic. This command never starts/stops services or mutates databases.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.runtime import configuration_errors

DIGEST = re.compile(r'^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[a-f0-9]{64}$')


def read_environment(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('Environment file must be a regular private file (0600)')
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) or name in values:
            raise ValueError(f'Invalid or duplicate environment assignment on line {number}')
        # Use literal env files, not shell commands or Compose interpolation.
        if value.startswith(('"', "'")) or '\x00' in value:
            raise ValueError(f'Use a literal unquoted environment value on line {number}')
        values[name] = value
    return values


def capacity(path='/'):
    usage = shutil.disk_usage(path)
    # Match df: reserved filesystem blocks are not deployable free capacity.
    result = {'disk_percent': round(100 * usage.used / (usage.used + usage.free), 1), 'disk_available_gib': round(usage.free / 2**30, 2)}
    memory = Path('/proc/meminfo')
    if memory.is_file():
        info = {line.split(':', 1)[0]: int(line.split()[1]) for line in memory.read_text().splitlines()}
        result.update(memory_available_gib=round(info['MemAvailable'] / 2**20, 2),
                      swap_percent=round(100 * (1 - info['SwapFree'] / info['SwapTotal']), 1) if info['SwapTotal'] else None)
    return result


def capacity_errors(state):
    errors = []
    if state['disk_percent'] >= 80 or state['disk_available_gib'] < 10:
        errors.append('Host needs disk below 80% used and at least 10 GiB available')
    if state.get('memory_available_gib', 0) < 6:
        errors.append('Host needs at least 6 GiB available memory for API, OCR worker, scanner and signature validation')
    if state.get('swap_percent') is None or state['swap_percent'] >= 80:
        errors.append('Host needs configured swap below 80% used')
    return errors


def compose_errors(config):
    errors = []
    services = config.get('services', {})
    for name in ('app', 'worker', 'scanner', 'scanner-init', 'scanner-updater'):
        service = services.get(name, {})
        if not service:
            errors.append('Missing service: ' + name)
            continue
        if not DIGEST.fullmatch(service.get('image', '')):
            errors.append(name + ' image must be pinned by SHA256 digest')
        if service.get('build') or not service.get('read_only') or not service.get('mem_limit') or not service.get('cpus'):
            errors.append(name + ' requires prebuilt image, read-only root, memory and CPU limits')
        if 'ALL' not in service.get('cap_drop', []) or not service.get('pids_limit'):
            errors.append(name + ' requires dropped capabilities and a PID limit')
        for port in service.get('ports', []):
            if port.get('host_ip') != '127.0.0.1':
                errors.append(name + ' must not expose public ports')
    dependency = services.get('worker', {}).get('depends_on', {}).get('app', {})
    if dependency.get('condition') != 'service_started':
        errors.append('Worker must start without waiting for API readiness')
    if services.get('scanner', {}).get('network_mode') != 'none':
        errors.append('Scanner must have no network access')
    return errors


def preflight(environment_file, release_file, compose_file, check_capacity=True):
    errors = []
    environment, release = read_environment(environment_file), read_environment(release_file)
    errors.extend(configuration_errors(environment))
    if environment.get('DOAIDE_ENVIRONMENT') != 'production':
        errors.append('Release environment must select production')
    process_env = {**os.environ, **release, 'DOAIDE_ENV_FILE': str(Path(environment_file).resolve())}
    result = subprocess.run(['docker', 'compose', '-f', str(compose_file), 'config', '--format', 'json'], env=process_env, capture_output=True, text=True)
    if result.returncode:
        errors.append('Docker Compose configuration is invalid; inspect privately (may contain secrets)')
    else:
        errors.extend(compose_errors(json.loads(result.stdout)))
    host = capacity() if check_capacity else None
    if host:
        errors.extend(capacity_errors(host))
        failed = subprocess.run(['systemctl', '--failed', '--no-legend', '--plain'], capture_output=True, text=True)
        if failed.returncode or failed.stdout.strip():
            errors.append('Target host must have no failed systemd units')
        containers = subprocess.run(['docker', 'ps', '--format', '{{.Status}}'], capture_output=True, text=True)
        if containers.returncode or any(word in containers.stdout.lower() for word in ('unhealthy', 'restarting')):
            errors.append('Target host has unhealthy or restarting containers')
    return {'ready': not errors, 'host': host, 'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--compose', default='compose.production.yml')
    parser.add_argument('--configuration-only', action='store_true', help='Validate files locally; does not certify target capacity')
    args = parser.parse_args()
    try:
        result = preflight(args.environment, args.release, args.compose, not args.configuration_only)
    except (ValueError, OSError) as exc:
        result = {'ready': False, 'errors': [str(exc) if isinstance(exc, ValueError) else 'Preflight dependency or file unavailable']}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['ready'] else 1)
