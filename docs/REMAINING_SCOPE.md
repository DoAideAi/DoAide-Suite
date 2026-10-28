# Remaining integration and release acceptance

28 October 2026 · v0.4

The v0.3 product-feature checklist has been implemented in the shared application. This does **not** establish that the twelve original scopes are production-complete. Original requirements remain in [SCOPE_OF_WORK.md](SCOPE_OF_WORK.md) and the individual scopes.

## Product-feature checklist addressed

| Product | Implementation added in v0.4 |
| --- | --- |
| Scope | Cited baseline comparison, uncertainty/review, Contracts clause import, real Invoicer draft endpoint |
| Collect | Case amounts/owners/evidence/outcomes, reminder sequences/contact caps, delivery reconciliation, customer history |
| AMC | Manufacturer/serial uniqueness, installation metadata, signed plans/windows, assigned technician links, start/before evidence/readings, renewal offer/acceptance/invoice |
| RFQ | Request/quote metadata, freight/packaging taxes and duties, clarification/revision/ranking history, comparison CSV/PDF |
| Tender | Portal/clarification metadata, mandatory/conditional/informational review and targeted amendments |
| Handover | Templates, contacts/categories, repair progress/bulk assignment, camera input and room/severity/photo reports |
| OrderDesk | Signed WhatsApp text/audio, reviewed transcription/candidates, variants/substitutions, overrides, freight/backorders, expiring reservations and invoice handoff |
| Batch | Effective recipes, structured costs, corrections/reversals, disposal, affected-order references and labels |
| Fees | Concessions, capped late-fee assessments, payment evidence, withdrawal and academic/finance permissions |
| Renew | Term start/length, negotiation history, renewal requests/confirmations and effective cancellation |
| SOP | Audience/tools/effective dates, recording review, branching templates, team/new-hire enrollment, reminders, signoff and offline expiry |
| ClaimPack | Ownership/deadline sources, reviewed reusable templates, provenance/conflicts and approved attachment redactions |

## Connections still open

- **Implemented, awaiting configured-account acceptance:** SMTP/recovery, Razorpay, Stripe test billing, Groq transcription, Meta WhatsApp intake/media, Contracts clause import and Invoicer draft creation. No real transactions or messages were sent. See [INTEGRATIONS.md](INTEGRATIONS.md).
- **Invoicer deployment dependency:** the existing service lacked a draft-create route. The real authenticated endpoint, migration and tests now exist on its local `codex/suite-invoice-handoff` branch. The complete patch is included here. Apply/migrate a test deployment and configure the workspace connection before accepting the deployed integration.
- **Remaining portfolio adapter implementation:** the broader scopes name Scheduler availability, Inventory catalogue/parts/lot receiving, Desk conversations/orders, Realty property references, Khata reconciliation, Proposals templates, Payroll rosters and course enrollment sources. These native adapters are not implemented by v0.4. Current workflows use explicit entries, retained files, CSV and external references. These dependencies are not marked complete.
- Inspection confirmed that Inventory exposes product/warehouse stock rather than the suite's lot-quality/expiry ledger, and Scheduler booking creation sends confirmations without the suite's retry-safe contract. Connecting them requires explicit data ownership/mapping and service contracts. A read-only stock snapshot must not be represented as synchronized inventory. Their production services were not changed.
- Direct vendor cancellation, tender-portal automation and automatic dispute submission remain later, separately authorized integrations, as stated in the original scopes.

## Release acceptance still open

1. **Current browser/mobile/accessibility acceptance:** the browser tool rejected the local URL. API/build/PDF checks pass, but historical screenshots do not certify v0.4 interaction or accessibility.
2. **Pilot/domain review:** representative inputs and approved tax/invoice documents, service plans, tender interpretation, provider packet/redaction rules, concessions/late fees, disposal, training and cancellation policies. The app records human decisions; it does not establish legal or third-party acceptance.
3. **Production environment:** validate deployment/database capacity, trusted proxy configuration, malware scanning, external monitoring/alerts, private off-site encrypted backups, key custody and target-host restore/rollback. The local container check is not production load acceptance.
4. **Retention/erasure policy:** encryption and workspace-data erasure tooling are implemented and tested. Approve actual retention periods, backup expiry and account closure before executing erasure. Account identities/memberships and provider-event deduplication identifiers remain outside the workspace-data eraser.
5. **Provider acceptance:** configured test credentials, prices and callback URLs are required. Enqueue/SMTP acceptance does not prove customer delivery; an exported packet is not a submission; a draft is not a finalized tax invoice.

No production deployment has been performed. Full original-scope acceptance remains open.
