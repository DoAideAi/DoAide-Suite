# Connection setup and verified contracts

Credentials stay on the server. External requests require `DOAIDE_DELIVERY_MODE=enabled`; local OCR does not. Jobs show blocked/failed/delivered outcomes. Review and explicitly retry blocked jobs after configuring a provider.

## Invoicer and Contracts

`DOAIDE_INVOICE_CONNECTIONS` is JSON keyed by suite workspace ID with `url` (full HTTPS draft endpoint) and `token` (authorized Invoicer JWT). Install the [real service adapter](../integrations/invoicer/README.md) first. The legacy global URL/token pair works only for a single-workspace database.

`DOAIDE_CONTRACTS_CONNECTIONS` has the same shape, with `url` ending in the inspected service's `/api` prefix. Scope → Import baseline from connected Contracts reads `GET /contracts/{id}` and `GET /contracts/{id}/clauses`, retains the exact response/hash and creates cited clauses. It requires a current draft/revision and reviewer/owner membership. Import never adopts an external model's assessment as a commercial decision.

Mappings must point to accounts authorized for the respective workspace. URLs/tokens are never accepted from browser requests or included in exports/job payloads. Cross-host redirects are not followed.

## WhatsApp orders

Configure `DOAIDE_META_APP_SECRET`, `DOAIDE_META_VERIFY_TOKEN`, `DOAIDE_META_ACCESS_TOKEN` and the Graph API version approved for your Meta application in `DOAIDE_META_GRAPH_VERSION`.

`DOAIDE_WHATSAPP_CHANNELS` maps each Meta phone-number ID to `{workspace_id, owner_id}`. Publish that workspace's catalogue first; the configured owner must remain a workspace owner.

- `GET /api/webhooks/whatsapp` validates the verify token/subscription challenge.
- `POST /api/webhooks/whatsapp` verifies exact-body HMAC in `X-Hub-Signature-256`, routes mapped numbers and deduplicates message IDs per channel. Text creates a draft retaining sender/time/source; it never confirms or reserves an order automatically.
- Audio download is a durable job. It retrieves Graph metadata, restricts downloads to Meta's HTTPS media host, rejects redirects/oversize/hash mismatches and retains original bytes for transcription/review.
- Unsupported message kinds are ignored. No outbound WhatsApp messages are sent by this adapter. Validate actual account permissions and callbacks with an authorized test number.

Reference: [Meta verification and signatures](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/). Current fixtures are synthetic; configured-account acceptance remains open.

## Recording transcription

Configure `DOAIDE_GROQ_TRANSCRIPTION_KEY`. OrderDesk/SOP accept WAV, OGG, MP3 or M4A up to 10 MiB. WAV duration is checked locally; provider-reported duration must be at most ten minutes. Users explicitly confirm permission to send the recording.

The worker calls [Groq transcription](https://console.groq.com/docs/speech-to-text) using `whisper-large-v3-turbo` and `verbose_json`. Original audio/hash and timestamped text are retained. Text remains `transcribed-needs-review` until a human reviews order text or procedure steps. Transcription never confirms orders, prices work, publishes procedures or acknowledges training.

## Existing providers and unconnected dependencies

SMTP/recovery, Razorpay and Stripe **test-mode-only** setup remain in [OPERATIONS.md](OPERATIONS.md). SMTP acceptance is not delivery confirmation. Collect records evidenced delivery/bounce/complaint outcomes; bounce/complaint reconciliation blocks pending reminders. Generic SMTP has no universal bounce callback; provider-specific relays require separate configuration.

v0.5 supplies real Inventory and Scheduler service contracts for OrderDesk stock and AMC appointments. Configuration, recovery, source patches and rollout boundaries are in [AUTHORITATIVE_CONNECTIONS.md](AUTHORITATIVE_CONNECTIONS.md). Batch fractional lots/quality, AMC parts, Desk, Realty, Khata, Proposals and staff/enrollment sources remain open in [REMAINING_SCOPE.md](REMAINING_SCOPE.md).
