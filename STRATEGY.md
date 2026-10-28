# DoAide Project Strategy

Last updated: 2026-10-14

## Deployment Principle

DoAide production servers should not build application code. The standard release path is:

1. Build the application locally or in CI.
2. Package only the runtime artifact into a small Docker image.
3. Push the image to a registry with an immutable tag.
4. Deploy by pulling that image on the server.
5. Verify health checks, then prune unused images and keep rollback tags available.

Production Compose files should use `image:` for application services. `build:` is allowed for local development Compose files, but not for production deploy files.

## Why This Matters

Small images help with disk pressure, image pulls, cold starts, and rollback speed. They also prevent build caches, source trees, `node_modules`, Python build wheels, and temporary artifacts from accumulating on small production disks.

Image size alone does not materially reduce live CPU or RAM once a service is already running. The runtime load comes from worker counts, duplicate services, database pressure, queue concurrency, health-check frequency, log volume, and memory-heavy dependencies. The footprint strategy therefore has two parts:

- Build footprint: small runtime images, no production builds, no build cache on servers.
- Runtime footprint: explicit worker limits, container memory/CPU limits where practical, light health checks, no duplicate units, and regular disk cleanup.

This matches the October 13 stabilization work: the biggest load reduction came from stopping broken duplicate services, fixing restart loops, lowering worker counts, and correcting bad database configuration. Docker image cleanup improved disk pressure and should become part of every deploy.

## Current Server Targets

| Server | Role | Architecture | Strategy |
| --- | --- | --- | --- |
| `89.167.8.178` | Primary DoAide product host | `linux/arm64` | Pull prebuilt arm64 images only. No app builds on host. |
| `204.168.241.124` | Secondary host for 409A, AutoApply, Trade | `linux/amd64` | Currently systemd-first and no Docker baseline. If containerized, pull prebuilt amd64 images only. |

When an image may run on both hosts, publish a multi-arch manifest for `linux/arm64,linux/amd64`. When it is primary-only, build `linux/arm64` to keep build time and storage low.

## Registry and Tags

Use GHCR unless a product already has a stronger registry convention.

Preferred naming:

```text
ghcr.io/r2st/<repo>-<service>:sha-<shortsha>
ghcr.io/doaideai/<product>-<service>:sha-<shortsha>
```

Rules:

- The DoAide organization's verified GitHub handle is `DoAideAi`; the suite repository is `DoAideAi/DoAide-Suite`. Registry names use lowercase. This namespace was checked on 2026-10-28; historical server notes below retain their original audit dates.

- Production deploys use immutable SHA tags or image digests.
- `latest` is not a production tag.
- Environment tags such as `prod` may exist as convenience pointers, but Compose should still be able to pin a SHA tag or digest.
- Images must not contain secrets, `.env` files, production database dumps, local credentials, or SSH keys.
- Add OCI labels for source revision and build date when practical.

## Production Compose Standard

Production Compose files should look like this shape:

```yaml
services:
  api:
    image: ghcr.io/r2st/gosumo-api:${IMAGE_TAG:?set IMAGE_TAG}
    pull_policy: always
    restart: unless-stopped
    env_file:
      - .env.production
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/health"]
      interval: 60s
      timeout: 10s
      retries: 3
```

Production deploy command:

```bash
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
docker image prune -f
```

Server-side deploy scripts should never run `docker compose build`, `npm install`, `pnpm install`, `pip install`, or framework build commands for production services.

## Image Minimization Rules

For Python services:

- Use multi-stage Dockerfiles.
- Build wheels in a builder stage; install only runtime dependencies in the final stage.
- Split `requirements.txt` from `requirements-dev.txt`.
- Keep `pytest`, test fixtures, linters, notebooks, and local-only tools out of runtime images.
- Use `--no-cache-dir` for pip installs.
- Avoid heavy ML/scientific packages unless the service actually needs them at runtime.

For Node services:

- Build locally or in a builder stage.
- Runtime image should contain only the server bundle or static `dist` output.
- Use `pnpm deploy`, Next.js standalone output, or equivalent production-only packaging.
- Do not ship source maps, tests, cache folders, or full monorepo workspaces unless required.

For static sites:

- Build static files locally or in CI.
- Serve with `caddy:2-alpine` or another tiny static server image.
- The products site already follows this pattern and should be treated as the reference implementation.

For all services:

- Add a `.dockerignore`.
- Run as non-root where practical.
- Use explicit health checks, but keep them cheap.
- Add memory/CPU limits for shared hosts when the service is not latency-critical.
- Separate application images from stateful backing services such as Postgres, Redis, MinIO, Qdrant, and NATS.

## Migration Plan

1. Classify every product as static, systemd artifact, or Docker service.
2. For active Docker services, convert production Compose files from `build:` to `image:`.
3. Add or repair `.dockerignore` files before the first image build.
4. Build images locally or in CI with `docker buildx`.
5. Push immutable tags to GHCR.
6. Deploy by setting `IMAGE_TAG`, running `docker compose pull`, and restarting only the affected service stack.
7. After successful health checks, remove server-side source trees, build caches, unused images, and obsolete containers.
8. Keep the previous image tag for rollback.

Baseline scan on 2026-10-13 found 30 Compose files under `/Users/dev/projects/Products` with `build:` directives. Those are the migration candidates. Not all are production deployments, so the first pass should prioritize active product sites.

Priority order:

1. Active container services on `89.167.8.178`, especially the largest runtime images.
2. Services with restart loops or heavy worker processes.
3. Static product sites that can be served from prebuilt files.
4. Secondary host services only after Docker is intentionally introduced there.

## Acceptance Gates

A service is considered aligned with this strategy when:

- Its production Compose file has no application `build:` directives.
- The server can deploy it with only `docker compose pull` and `docker compose up -d`.
- The runtime image excludes dev/test dependencies and local build caches.
- The service has a health check and a documented rollback tag.
- The server remains below agreed CPU, memory, swap, and disk thresholds after deploy.

## Operating Targets

Shared production hosts should aim for:

- `systemctl --failed` equals zero.
- No Docker containers in restart loops or permanent unhealthy state.
- Root disk below 80% used, with alerting before 85%.
- Swap available during normal operation, not permanently saturated.
- No duplicate systemd and Docker deployment for the same product role.

The deployment strategy is therefore not just "smaller Docker images"; it is "build elsewhere, ship small, run fewer things, cap expensive things, and keep production boring."

## DNS Automation

Cloudflare DNS changes for `doaide.com` can be made from this workspace with the ignored env file:

```text
/Users/dev/Documents/doaide/.secrets/cloudflare-doaide.env
```

The token is scoped to `Zone DNS Edit` for the `doaide.com` zone only. Do not commit `.secrets/`.

Reusable helper:

```bash
/Users/dev/Documents/doaide/ops/cloudflare-upsert-a.sh prospect 89.167.8.178 false
```

Use DNS-only records for the Caddy-backed product sites unless there is a specific Cloudflare proxy reason.

## First Migration

Completed on 2026-10-13:

- Landline/Realty Celery was rebuilt off-server on the local workstation using Colima/Docker Buildx.
- The server received a Docker image tar and loaded it with `docker load`; no application build ran on production.
- `landline-celery` now runs `ghcr.io/apprend-technologies/landline-backend:doaide-slim-20261013162031`.
- The prior `backend-celery-worker:latest` image was removed after the new container reported healthy.
- The active custom image footprint went from `backend-celery-worker:latest` at about `1.02GB` in `docker images` to the slim Landline image at about `743MB`.

Local artifact:

```text
/Users/dev/Documents/doaide/artifacts/landline-backend-doaide-slim-20261013162031.tar
```

## Consent and Cleanup Cycle

Completed on 2026-10-13:

- AutoApply's Gmail/email AI processing is off until separately recorded,
  versioned consent. Existing accounts were not opted in. Requests check consent
  before external attempts and restrict routing to OpenRouter no-data-collection
  and zero-retention endpoints; unsafe provider fallback is not permitted.
- Google Auth Platform now links the correct AutoApply privacy policy and
  declares the same five scopes as the runtime. Updated justifications were
  saved, and a follow-up was sent in the existing Google review thread with a
  non-admin, synthetic-only review account. Approval and a refreshed authorized
  OAuth demo remain pending; do not describe the Google block as resolved.
- AutoApply's frontend was built locally from a snapshot of production source,
  preserving its custom public pages. Only scoped backend changes and built
  frontend assets were deployed, with an encrypted DB backup and source rollback.
- Removed one unused Voice deployment, three August CAFlow releases, and build
  dependencies from six static sites that use the global `serve` runtime. An
  off-server archive was validated first. Current October rollback releases,
  live environments, databases, uploads, and Docker volumes were preserved.
- Primary root disk decreased from 84% to 80%, with about 7.3 GiB free. All six
  affected public sites and their JavaScript assets returned HTTP 200 afterward.
  Both hosts had zero failed systemd units. This improves headroom but does not
  yet beat the below-80% target; Docker images remain approximately 3.299 GB.

The recovery archive is under ignored `ops/archives/` with mode 600 and contains
deployment secrets. Keep it private. Build-only dependencies should not be
shipped in future static-site releases; verify the runtime path before removing
them. A live application's largest directory is not automatically disposable.

## Encrypted Application Storage

AutoApply on the secondary host now uses isolated PostgreSQL and Redis services
on an application-specific LUKS volume. Database files, WAL, SQL logs, artifacts,
and scheduler state stay on that volume; dependent services check its mount
before startup. Redis is loopback-only and password-protected. Swap uses a fresh
volatile encryption key per boot. Other applications' database storage was not
moved. Root-only unlock keys have protected recovery copies off-server; this is
not hardware-backed key management or whole-host encryption.

Managed AutoApply backups use a separate encryption key, daily systemd backup
timer, and 30-day retention. Encrypt/decrypt verification precedes retirement of
plaintext archives. Restore tests must pass before retiring legacy database
copies. Never treat encrypted backups as proven recoverable until a restore and
the off-host recovery key have both been tested. Changes to consent must also be
tested through the real frontend request layer, not just mocked component APIs.

The October 14 reviewer evidence walkthrough is synthetic-only, demonstrates
working opt-in and revocation, and is not a successful Gmail OAuth grant video.
Google approval remains pending. The protected Gmail AI route still receives
OpenRouter HTTP 402; do not remove retention or training restrictions to obtain
a cheaper fallback. Any newly eligible AI processor needs verified account
privacy settings and updated, affirmative user disclosure/consent before use.

October 14 operational checks: fixed primary logrotate failure caused by a
backup config loaded as active config; removed generated dependencies from six
additional static frontends only after runtime and asset checks. All six passed
HTML/JavaScript comparisons after restart. Primary root disk is 79% used with
7.7 GiB free; secondary is 49% with 19 GiB free. Both hosts have no failed systemd
units. Trade's dashboard now binds loopback rather than all interfaces; its
public Caddy route still returns HTTP 200.

Later October 14 update: a dedicated Groq key was explicitly authorized, created
with a January 12, 2027 expiry, and securely deployed. Inference ZDR was enabled
in that key's owning account. Gmail routing now permits this exact, recently
verified key at the standard chat-completions endpoint, with approved base models
only. Its attestation expires after 30 days and must be manually reverified;
key changes invalidate it. Consent revision `2026-10-14` explicitly discloses Groq
and does not carry old consent forward. A live synthetic reviewer test returned
`INTERVIEW` through this protected route; subsequent consent revocation blocked
calls. Actual users remain opted out. Google OAuth clearance is still pending.

Google follow-up submitted October 14 in existing thread, message
`1a1388a837f4af3f`: the supplementary private-AI walkthrough plus three Google
diagnostic/review screenshots were verified as SENT attachments. Production
authorization requests now disable merging old granted scopes. Existing users
were not disconnected; connected-grant audit found no extra scopes. Fresh
diagnostics remain account-specific (unverified warning versus hard block), so
formal clearance is not established. The existing Console scope list and
production audience remain unchanged. A pre-existing InsureKit client shares
the project; do not delete or rotate it casually to resolve review requirements.

## Product Backend Audit and Repairs

October 14 follow-up:

- Browser smoke sweep: 49 public product entry points returned HTTP 200 with
  no uncaught JavaScript errors at 390px. This is entry-point coverage, not
  certification of every authenticated feature or integration.
- Comply: fixed mobile navigation overflow and keyboard handling in the Free
  Tools menu. Built off-server from a production-source snapshot, preserving
  its deployed design. All 86 frontend tests passed; production navigation
  passed at 320, 390, 768, and 1440px.
- Analytics (`insights.doaide.com`): corrected the localhost API URL and Caddy
  prefix rewrite; rejected logins retain their visible error. Added database
  pool pre-ping and a database-backed health check that returns 503 on failure.
  All 54 frontend and 16 isolated backend tests passed. Production browser
  login with nonexistent synthetic credentials now reaches the database-backed
  API and returns 401, rather than a connection error or HTTP 500.
- Med: its configuration pointed at Prospect's PostgreSQL port and a missing
  database. The user confirmed no existing users and explicitly authorized an
  empty replacement. Created isolated `documedic_db` with a non-superuser owner
  on native PostgreSQL port 5432, leaving Prospect untouched. Applied migrations
  through `0044`; startup seeded 50 drug records, 35 interactions, and 27
  contraindications. Public readiness returns 200. Verified browser signup,
  synthetic patient create/read/update/soft-delete, cross-account isolation,
  token refresh, and logout revocation. Two synthetic QA accounts and the
  soft-deleted synthetic chart remain for audit provenance. No real clinical
  data or inference requests were used.
- Invoicer, Inventory, Contracts, Payroll, and Scheduler backend tests passed
  against isolated fixtures: 88, 21, 69, 55, and 35 tests respectively. Including
  Analytics, 284 backend tests passed. Proposals' local suite was not completed
  because its isolated environment lacked Jinja2; live health and anonymous
  authentication checks passed.
- Thirteen discovered anonymous account endpoints returned 401. 409A dependency
  readiness passed; AutoApply database and broker passed; Trade health reported
  PAPER mode. No payments, trades, or outbound messages were sent.
- Brand-site catalogue links restored for FinCalc (`calc`), PitchCraft (`pitch`),
  Convert (`tools`), and reachable Shayari. There are 38 active catalogue entries
  and nine product redirects. All 94 static source pages passed internal-link
  validation; production smoke passed after Pages deployment `81691949`.

Rollback copies for Comply and Analytics are under each product's
`frontend/releases/pre-audit-20261014/`; old static assets were preserved.
Analytics Caddy rollback: `/opt/knol/Caddyfile.pre-analytics-audit-20261014`.
Med's previous environment and new database recovery configuration are private
root-only files under `/opt/documedic/`; never include their values in reports.
Application builds and dependency installation occurred off-server.

Remaining: Realty's WhatsApp token is expired; Desk's vector dependency is
unreachable (PostgreSQL and Redis are up). Six catalogue products remain
unpublished/unreachable: DPDP, PaySlip, RentBanao, PDF, Legal, EMIBuddy. Google
OAuth approval for AutoApply remains pending. Full provider/payment workflows,
every tool within each product, clinical correctness, and every authenticated
customer workflow were not certified. Med still needs a verified recurring
backup/restore process before real clinical use.

Post-deploy: zero failed systemd services on both hosts, no unhealthy/restarting
containers in the primary snapshot, primary disk 79%, secondary disk 49%.
Repeatable checks and deployment scripts are in `ops/`; JSON evidence is in
`ops/evidence/product-audit-20261014/`.

## October 25 Recovery Pass

The project repositories have moved to `/Users/dev/projects/doaide/`.
The earlier status above is historical, not current deployment status.

- All six restored products (DPDP, PaySlip, RentBanao, PDF, Legal, EMIBuddy)
  passed HTTPS, 390px/1440px layout, JavaScript-error and representative API
  checks. Synthetic exports, agreement preview, compliance scoring, zero-rate
  EMI calculation, PDF merge and browser HTML export passed. Arbitrary URL
  conversion remains intentionally disabled. This does not certify every tool,
  legal/financial correctness, or external AI integration.
- PDF export was failing because `/tmp/doaide-pdf` belonged to root while the
  renderer runs as www-data. Deployed a durable tmpfiles owner/mode correction
  (0700 www-data); verified rendering as the production identity and through
  the public browser. Existing completed-export cleanup and hourly expiry remain.
- Desk's API was restarting because its entire `apps/api/dist` directory was
  absent. Downloaded a production source snapshot, confirmed it exactly matched
  local source, type-checked and compiled locally, then deployed only compiled
  output with a production-source hash guard. Public readiness now reports
  database, Redis and vector storage up. Qdrant itself had remained running.
  The cause of the deleted build was not established; avoid destructive
  in-place builds of the running API in future deployment work.
- 409A has moved to the primary host. Its daily backup worked, but weekly
  restore verification lacked `/etc/n409/backup-verify.env`. Fixed its
  provisioning script's psql variable interpolation (stdin SQL, not `-c`,
  with ON_ERROR_STOP), passed all 20 focused tests, and provisioned the separate
  non-superuser maintenance role without widening the application role.
  A real restore passed: 103 tables and 176 migrations. Scratch DB was removed.
- Main-site browser regression expectations updated to the current 10 flagship
  cards and 46 directory tools. Production smoke passed desktop/mobile layout,
  search, category filtering, FAQ keyboard state, four tool workflows, and all
  15 redirects. No new brand-site deployment was necessary for test-only edits.
- Med's encrypted daily local backups are succeeding; latest observed backup
  was October 24 at 20:30 UTC. The initial October 14 off-host restore verified
  34 tables, 100 stored files and recovery configuration. Current off-host
  status is NOT verified: 204.168.241.124 rejects both documented deployment
  keys and the saved root password in `/Users/dev/projects/keys`. User was
  informed; do not assume the off-host timer is still working.
- Post-repair primary host: zero failed systemd units. Realty still reports
  an expired WhatsApp token. Google OAuth approval has not been re-established
  by this pass. No real payments, trades or outbound messages were initiated.

Recovery scripts: `ops/fix-pdf-temp-permissions.py`,
`ops/repair-409-backup-verification.py`, `ops/restore-desk-build.py`.
The 409A provisioning-script rollback copy has suffix `.pre-20261025` on host.
