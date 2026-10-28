import socket
from datetime import datetime, timezone

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(3)
    client.connect('/run/clamav/clamd.sock')
    client.sendall(b'zVERSION\0')
    reply = bytearray()
    while b'\0' not in reply and len(reply) < 4096:
        chunk = client.recv(4096 - len(reply))
        if not chunk:
            raise SystemExit(1)
        reply.extend(chunk)
    date = bytes(reply).split(b'\0')[0].decode().split('/', 2)[2]
    age = (datetime.now(timezone.utc) - datetime.strptime(date, '%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc)).total_seconds()
    raise SystemExit(0 if -3600 <= age <= 72 * 3600 else 1)
