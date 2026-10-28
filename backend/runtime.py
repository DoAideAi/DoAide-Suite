"""Validate production boundaries without printing connection secrets."""
import ipaddress
import os
from urllib.parse import urlsplit


def production():
    return os.environ.get('DOAIDE_ENVIRONMENT', 'development') == 'production'


def registration_open():
    return os.environ.get('DOAIDE_REGISTRATION_MODE', 'closed' if production() else 'open') == 'open'


def configuration_errors(env=None):
    env = os.environ if env is None else env
    errors = []
    if env.get('DOAIDE_ENVIRONMENT', 'development') not in ('development', 'production'):
        errors.append('DOAIDE_ENVIRONMENT must be development or production')
    if env.get('DOAIDE_ENVIRONMENT') != 'production':
        return errors
    try:
        url = urlsplit(env.get('DOAIDE_PUBLIC_URL', ''))
        url.port
    except ValueError:
        url = urlsplit('')
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.path not in ('', '/') or url.query or url.fragment):
        errors.append('DOAIDE_PUBLIC_URL must be a bare HTTPS origin')
    for name in ('DOAIDE_REQUIRE_WORKER', 'DOAIDE_REQUIRE_MALWARE_SCAN'):
        if env.get(name) != 'true':
            errors.append(name + ' must be true in production')
    if not env.get('DOAIDE_CLAMD_SOCKET', '').startswith('/'):
        errors.append('DOAIDE_CLAMD_SOCKET must be an absolute private Unix socket path')
    addresses = env.get('FORWARDED_ALLOW_IPS', '').split(',')
    try:
        for address in addresses:
            if ipaddress.ip_network(address.strip(), strict=False).prefixlen == 0:
                raise ValueError
    except ValueError:
        errors.append('FORWARDED_ALLOW_IPS must contain explicit trusted proxy IPs or restricted CIDRs')
    if not env.get('DOAIDE_DB_PATH', '').startswith('/'):
        errors.append('DOAIDE_DB_PATH must be an absolute persistent path')
    registration = env.get('DOAIDE_REGISTRATION_MODE', 'closed')
    if registration not in ('open', 'closed'):
        errors.append('DOAIDE_REGISTRATION_MODE must be open or closed')
    if registration == 'open' and env.get('DOAIDE_REQUIRE_VERIFIED_EMAIL') != 'true':
        errors.append('Public production registration requires verified email')
    if env.get('DOAIDE_REQUIRE_VERIFIED_EMAIL') == 'true':
        if env.get('DOAIDE_DELIVERY_MODE') != 'enabled' or not all(env.get(k) for k in ('DOAIDE_SMTP_HOST', 'DOAIDE_SMTP_FROM')):
            errors.append('Verified email requires enabled and configured SMTP delivery')
    return errors


def validate_runtime():
    errors = configuration_errors()
    if errors:
        raise RuntimeError('; '.join(errors))
