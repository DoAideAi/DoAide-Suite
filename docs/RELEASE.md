# Release and deployment procedure

29 October 2026 · v0.6.1 · schema 5

The application workflows and portfolio adapter source are implemented. This
release adds a production runtime, real local ClamAV scanning, shutdown handling,
capacity/configuration gates, an off-site backup controller and monitoring probes.
These tools do not provision a host, activate provider accounts or approve business
policies. Browser/mobile acceptance remains unverified because the browser tool
rejected the local URL; no alternate browser route was used.

## Host decision

The read-only inspection of the existing primary host, `89.167.8.178`, failed the
deployment gate: about 81% disk usage (rounded to 82% by `df`), 6.74 GiB free disk,
1.39 GiB available RAM and 98.9% swap usage. No production service was changed.
See [host evidence](evidence/production-host-preflight.json).

Use a dedicated Linux host with at least 8 GiB RAM, sufficient CPU for OCR and
signature validation, encrypted persistent storage and configured swap. The
preflight requires **6 GiB available RAM, 10 GiB free disk, disk below 80%, swap
below 80%, no failed systemd units and no unhealthy/restarting containers**. Disk
capacity must also cover the projected evidence volume and retained releases.
Production changes to the existing shared host require a separate capacity plan;
do not stop other products or prune their recovery images to make this release fit.

## Build and verify off-server

`make release-check` builds the API, OCR worker and scanner, then exercises the
actual production Compose file with temporary volumes, synthetic accounts and
real ClamAV definitions. It covers cold startup, closed registration, owner login,
secure cookies, host rejection, clean upload, EICAR rejection, worker stop/start,
scanner outage and SQLite backup/isolated restore. It deletes only its uniquely
named test containers and volumes. Public signature downloads are required.

The manually invoked **Build verified release images** GitHub workflow repeats
the checks and publishes all three images for `linux/amd64` and `linux/arm64` to
GHCR. The artifacts contain immutable image digests. It does not deploy. Keep the
previous release's digests and environment file for rollback. Never build on the
production server.

The scanner uses the official ClamAV 1.4.6 LTS image pinned by digest. Its daemon
has no network interface; only the updater can download signatures. API and
worker stream bytes through a private Unix socket. Definitions older than 72
hours, scanner errors, limit violations and ambiguous replies all fail closed.
Signature validation needs up to 2 GiB, independently of the daemon. Review
ClamAV security updates and republish the pinned scanner regularly. References:
[ClamAV command protocol](https://github.com/Cisco-Talos/clamav/blob/main/docs/man/clamd.8.in),
[official images](https://github.com/Cisco-Talos/clamav-docker),
[Compose dependency semantics](https://docs.docker.com/compose/how-tos/startup-order/).

## Prepare an approved target

Install Docker and Compose supporting `env_file.format: raw` (Compose 2.30+).
Copy the release Compose file and `scripts/release_preflight.py` with
`backend/runtime.py` to `/opt/doaide-suite`. Create private, mode-0600
`release.env` and `.env.production` files. Do not commit either file.

`release.env` contains the published `DOAIDE_IMAGE`, `DOAIDE_WORKER_IMAGE` and
`DOAIDE_SCANNER_IMAGE` digests, plus optional `DOAIDE_PORT` (default 8012).
Use [production.env.example](../deploy/production.env.example) for the runtime
environment. Set the approved HTTPS origin and exact proxy IP/CIDR as seen by
the app container. Never trust all forwarded addresses. Environment values are
literal and unquoted; `$` in a provider password is not interpolated.

Validate without printing the resolved environment (it can contain secrets):

```sh
python3 scripts/release_preflight.py --environment .env.production --release release.env
docker compose --env-file release.env -p doaide-suite -f compose.production.yml pull
docker compose --env-file release.env -p doaide-suite -f compose.production.yml up -d --wait --wait-timeout 300
```

The application binds only to host loopback. Merge an approved route into the
existing HTTPS proxy; [Caddyfile.example](../deploy/Caddyfile.example) is for a
**host-native** Caddy process. The current shared host uses containerized Caddy,
so that example cannot be pasted into its proxy without a reviewed network route.
Verify certificate, forwarded scheme/client identity, Origin checks, secure
cookies and absence of public API/scanner ports before routing users. Keep token
URLs out of proxy access logs. Choose and configure the actual domain first.

Registration defaults to closed in production. Bootstrap the first pilot owner
inside the API container; the command prompts for a hidden password, never resets
existing identities and does not assert email verification:

```sh
docker compose --env-file release.env -p doaide-suite -f compose.production.yml exec app python scripts/bootstrap_owner.py --email owner@example.com
```

Use the owner's real approved email. Keep `DOAIDE_DELIVERY_MODE=disabled` for a
closed pilot until SMTP and other provider accounts are explicitly configured
and tested. Opening registration requires `DOAIDE_REGISTRATION_MODE=open`,
`DOAIDE_REQUIRE_VERIFIED_EMAIL=true` and functioning SMTP delivery. Existing pilot
owners must verify their email when verification is enabled. Starting a worker
with delivery enabled can process existing queued jobs: review them first.

## Independent backup and monitoring host

Run `scripts/offsite_backup.py` on a separate host with the Suite's locked Python
dependencies, SSH client and a private encryption key stored separately from the
backup destination. Pin SSH host keys and restrict the account/command used to
read the snapshot. The controller pulls a consistent snapshot over SSH, encrypts
it locally, decrypts it into an isolated temporary directory and verifies SQLite
integrity before writing a checksum receipt. The key is never sent to the app
server. New filenames are mandatory; no backup or business data is auto-expired.

```sh
uv run python scripts/encrypted_backup.py --create-key --key-file /private/keys/suite.key
uv run python scripts/offsite_backup.py --host APPROVED_APP_SSH_ALIAS --directory /opt/doaide-suite --key-file /private/keys/suite.key --output /private/backups/suite-UNIQUE_TIMESTAMP.enc
uv run python scripts/monitor_release.py --url https://APPROVED_DOMAIN --backup-directory /private/backups --metrics /private/metrics/suite.prom
```

Choose approved storage, key recovery custody and backup expiry before installing
a daily schedule. A successful receipt proves snapshot transfer and restoration
at that time, not future recoverability after key loss. The current tool supports
databases up to 512 MiB; move to streaming backup infrastructure before that size.
Do not leave plaintext restores outside a protected temporary directory.

The monitor verifies public HTTPS readiness/certificate and, when supplied,
backup age (under 26 hours), size and SHA256. `--host` additionally checks the host
on which the monitor runs; use that option on the app host, not the independent
monitor host. It writes Prometheus gauges and exits nonzero on failure. Connect
the gauge, stale probe timestamp and failed unit state to an **approved alert
route**. No email/webhook is sent by the tool. The provided systemd service/timer
are installation templates, not already active monitoring.

## Upgrade, restore and rollback

Before an upgrade, put the route in maintenance, stop the worker, finish/reconcile
in-flight provider work, and take a verified off-site backup. Stop the API before
changing its database volume. Start the replacement release with the same volume
only for compatible additive migrations. Workers respond to SIGTERM, finish the
current job and stop; after the 120-second grace period, a killed job still needs
lease/provider reconciliation.

To restore, decrypt a selected backup into a **new** protected volume, verify
integrity/counts with the selected image, start exactly one API/worker pair with
delivery disabled, and check read-only sample records/documents before changing
traffic. Preserve the previous volume and image. Never roll an older application
back onto a newer schema blindly. A database rollback cannot undo an external
message, booking, reservation or payment.

The original pilot/domain, provider-account, browser/mobile and retention-policy
acceptance gates are retained in [REMAINING_SCOPE.md](REMAINING_SCOPE.md). The
Inventory, Scheduler, Invoicer and Khata changes also need their own approved
test deployments and configured workspace accounts before live activation.
