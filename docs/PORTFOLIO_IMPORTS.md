# Portfolio source imports · v0.6

All imports use workspace-specific server credentials, bounded responses, no redirects, source identity checks and the durable job queue. Enable external connections only in a configured test environment. A completed fetch creates an immutable **Imported source preview** and a private source file; it does not confirm an order, post a payment, verify evidence, invite a user or accept a contract. Review the preview and use the matching apply action. A changed record or revoked reviewer permission blocks an outstanding import.

## Connections

Set each environment variable to a JSON object keyed by Suite workspace ID. Each value contains `url`, `token` and the identity below. Tokens remain server-side and must be rotated before expiry. `DOAIDE_DELIVERY_MODE=enabled` permits the worker to fetch; it defaults to disabled.

| Variable | URL suffix | Required identity | Actual source contract |
| --- | --- | --- | --- |
| `DOAIDE_DESK_CONNECTIONS` | `/v1` | `business_id`: UUID string | `GET /conversations/{uuid}`, paginated `/messages`; `GET /orders/{uuid}` |
| `DOAIDE_REALTY_CONNECTIONS` | `/api` | `agent_id`: integer | `GET /properties/{id}` |
| `DOAIDE_PROPOSALS_CONNECTIONS` | `/api` | `business_id`: integer | `GET /auth/me`, `GET /templates/{id}` |
| `DOAIDE_PAYROLL_CONNECTIONS` | `/api/v1` | `business_id`: integer | `GET /auth/me`, `GET /employees?skip=&limit=` |
| `DOAIDE_KHATA_CONNECTIONS` | `/api` | `account_email`: exact account email | `GET /ledger` from the included Khata service patch |

Example (synthetic only):

```json
{"workspace-id":{"url":"https://proposals.example/api","token":"PRIVATE","business_id":1}}
```

## Product actions

- **OrderDesk:** preview a Desk conversation or order, then apply reviewed source text. Conversation pagination retains message IDs, timestamps and directions; only inbound text becomes order input. Parsing and customer confirmation remain explicit. Desk's own order service has a separate stock ledger: imported orders are source evidence, not a bidirectional fulfillment sync. Confirm the intended fulfillment ownership before operating both services against the same goods.
- **ClaimPack:** apply Desk conversation/order sources as evidence, then use normal evidence verification, redaction and packet review. Imported previews never become verified evidence automatically. Raw preview objects are excluded from document narratives so an approved redacted attachment cannot leak through the preview.
- **Handover:** preview and apply a Realty property reference. The property identity, location and retained details enter the handover record without altering the upstream property or automatically closing snags.
- **Scope:** preview and apply a Proposals offer template. Reviewed sections, terms and reference pricing are retained with the offer. Estimate pricing, commercial approval and client acceptance remain explicit; a template is not a signed contract baseline.
- **Collect:** preview one Khata customer's synced ledger, then select an active `received` transaction. Confirm the collection record's customer name and record the matching reason. The transaction posts an immutable payment with a source-derived reference unique across the workspace. An overpayment, future payment or duplicate source cannot post. Later Khata edits/deletions do not rewrite history; reconcile corrections through explicit financial entries. Unsynced browser-only Khata data must be synced in Khata first.
- **SOP:** preview the Payroll roster, then select employee IDs and a due date for a published procedure. Only active staff whose email already belongs to the workspace can be assigned. No invitations or account access are created. Salary, bank, PAN, UAN, phone and birth-date fields are discarded before retention. Roster files and previews are excluded from released procedure PDFs/packets.
- **Fees:** upload a course enrollment CSV, preview it and select a student/course pair. Confirm the existing fee record's student name/reference. Import does not overwrite agreed fees, schedules or payment history. Existing enrollment records require explicit amendment rather than a second import.

Enrollment CSV headers are `student_reference,course_reference,start,end,terms`; dates use `YYYY-MM-DD`. One file is limited to 200 KB and 1,000 rows. Duplicate student/course pairs, missing values and reversed dates reject the whole preview. Additional columns are ignored rather than treated as fees or consent.

## Limits and evidence

Desk imports cap a conversation at 1,000 messages. Payroll caps a roster at 10,000 employees. Each response is streamed with a 2 MB bound and each retained preview is limited to 200 KB. Larger sources must be split or selected more narrowly; they never truncate silently. Remote media URLs are retained only as references and are not downloaded by this adapter.

`uv run python scripts/check_sources.py` starts real Proposals, Payroll and Khata applications against temporary databases and exercises the Suite imports over HTTP. Their sibling `backend/.venv` environments must be installed. Desk and Realty contracts are checked against their actual controller/serializer code and covered by tenant, pagination, retention and explicit-review tests using deterministic responses. Deployed accounts, TLS and real source permissions remain acceptance checks; no production services are contacted by these scripts.
