"""Product-specific input contracts; shared by validation and the editor."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def field(key, label, kind="text", **kwargs):
    return {"key": key, "label": label, "type": kind, "required": True, **kwargs}


def rows(key, label, columns):
    return field(key, label, "rows", columns=columns)


def product(slug, name, subtitle, buyer, category, fields, sample, deliverable):
    return {"slug": slug, "name": name, "subtitle": subtitle, "buyer": buyer,
            "category": category, "fields": fields, "sample": sample,
            "deliverable": deliverable, "stage": "Operational local build"}


TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()
future = lambda days: (TODAY + timedelta(days=days)).isoformat()
money = lambda key, label, **kw: field(key, label, "number", **{"min": 0, "max": 1_000_000_000, **kw})
integer = lambda key, label, **kw: field(key, label, "number", **{"min": 0, "max": 1_000_000, "integer": True, **kw})
select = lambda key, label, choices: field(key, label, "select", options=choices)

PRODUCTS = [
    product("scope", "Scope", "Keep extra work visible. Get the change agreed.", "Agencies & independent studios", "Revenue", [
        field("client", "Client"), field("baseline", "Agreed deliverables · one per line", "textarea"),
        field("request", "New client request", "textarea"), money("hours", "Estimated extra hours"),
        money("rate", "Hourly rate · INR"), integer("extra_days", "Additional delivery days"),
        select("decision", "Your scope assessment", ["Unreviewed", "In scope", "Change required", "Needs clarification"])
    ], {"client": "Acme Studio", "baseline": "Five-page marketing website\nContact form\nTwo design revision rounds", "request": "Add a customer login and subscription dashboard", "hours": 18, "rate": 2000, "extra_days": 4, "decision": "Unreviewed"}, "Change request"),
    product("collect", "Collect", "Know what is owed and what needs a follow-up.", "Service businesses & distributors", "Revenue", [
        field("customer", "Customer"), field("invoice", "Invoice reference"), money("amount", "Invoice amount · INR"),
        money("paid", "Total recorded payments · INR"), field("due", "Due date", "date"),
        field("promise", "Promised payment date", "date", required=False),
        select("disputed", "Payment disputed?", ["No", "Yes"]), field("notes", "Follow-up notes", "textarea", required=False)
    ], {"customer": "Northstar Design", "invoice": "INV-2026-104", "amount": 85000, "paid": 25000, "due": future(-12), "promise": future(2), "disputed": "No", "notes": "Customer expects the next payment after project handover."}, "Collection brief"),
    product("amc", "AMC", "Every asset, included visit, and renewal in view.", "RO, AC & equipment service teams", "Operations", [
        field("customer", "Customer"), field("asset", "Equipment and serial number"),
        field("start", "Contract start", "date"), field("end", "Contract expiry", "date"),
        integer("included", "Included service visits"), integer("completed", "Completed visits"),
        field("next_visit", "Next service date", "date", required=False), money("contract_value", "Contract value · INR")
    ], {"customer": "Greenleaf Cafe", "asset": "RO purifier · RO-042", "start": future(-340), "end": future(25), "included": 4, "completed": 3, "next_visit": future(5), "contract_value": 7200}, "Service and renewal plan"),
    product("rfq", "RFQ", "Compare the full cost of supplier quotations.", "Procurement teams & manufacturers", "Operations", [
        field("item", "Item and specification"), integer("quantity", "Required quantity", min=1),
        rows("quotes", "Supplier quotations · all amounts in INR", [field("supplier", "Supplier"), money("unit_price", "Unit price"), money("freight", "Freight"), money("tax_percent", "Tax %", max=100), integer("lead_days", "Lead days"), field("exclusions", "Exclusions", required=False)])
    ], {"item": "Stainless steel bottle · 750 ml", "quantity": 500, "quotes": [{"supplier": "Atlas Metals", "unit_price": 155, "freight": 1800, "tax_percent": 18, "lead_days": 14, "exclusions": "Branding not included"}, {"supplier": "River Works", "unit_price": 162, "freight": 0, "tax_percent": 18, "lead_days": 9, "exclusions": ""}]}, "Quotation comparison"),
    product("tender", "Tender", "Turn bid requirements into a preparation checklist.", "Small businesses bidding for contracts", "Operations", [
        field("authority", "Buyer or issuing authority"), field("deadline", "Submission date", "date"),
        field("source", "Tender excerpt · paste requirement lines", "textarea"),
        field("available", "Available documents · one name per line", "textarea", required=False)
    ], {"authority": "Example Facilities Buyer", "deadline": future(21), "source": "Required: company registration certificate\nRequired: two customer references\nMust provide: equipment maintenance plan\nDelivery location: Pune", "available": "company registration certificate\ntwo customer references"}, "Bid preparation checklist"),
    product("handover", "Handover", "Close the snags before the project changes hands.", "Interior studios & property managers", "Operations", [
        field("client", "Client or property owner"), field("site", "Site or property"),
        rows("issues", "Snag register", [field("room", "Room / area"), field("description", "Issue"), select("severity", "Severity", ["Minor", "Major", "Critical"]), field("assignee", "Assigned to"), select("status", "Status", ["Open", "Fixed", "Verified"])])
    ], {"client": "Example Property Owner", "site": "Apartment 302", "issues": [{"room": "Kitchen", "description": "Loose cabinet hinge", "severity": "Major", "assignee": "Installation team", "status": "Open"}, {"room": "Bedroom", "description": "Paint touch-up", "severity": "Minor", "assignee": "Finishing team", "status": "Fixed"}]}, "Handover checklist"),
    product("orderdesk", "OrderDesk", "Turn a written order into a checked order draft.", "Wholesalers & distributors", "Revenue", [
        field("customer", "Customer"), field("order_text", "Order lines · quantity × SKU or exact product name", "textarea"),
        rows("catalog", "Product catalogue · INR", [field("sku", "SKU"), field("name", "Product"), money("price", "Unit price"), integer("stock", "Available units")])
    ], {"customer": "Corner Store", "order_text": "12 x TEA-250\n6 x Coffee 200g", "catalog": [{"sku": "TEA-250", "name": "Tea 250g", "price": 120, "stock": 40}, {"sku": "COF-200", "name": "Coffee 200g", "price": 240, "stock": 20}]}, "Checked order draft"),
    product("batch", "Batch", "Trace ingredient lots and understand batch cost.", "Small food & specialty manufacturers", "Operations", [
        field("product", "Finished product"), field("batch_number", "Batch reference"),
        integer("planned_units", "Planned finished units", min=1), integer("produced_units", "Actual finished units", min=1),
        field("expiry", "Finished batch expiry", "date"), money("overhead", "Batch overhead · INR"),
        rows("ingredients", "Ingredients consumed", [field("name", "Ingredient"), field("lot", "Supplier lot"), money("quantity", "Consumed quantity", min=0.001), field("unit", "Unit"), money("unit_cost", "Cost per unit · INR")])
    ], {"product": "Almond cookies · pack", "batch_number": "B-2026-041", "planned_units": 100, "produced_units": 92, "expiry": future(90), "overhead": 900, "ingredients": [{"name": "Flour", "lot": "FL-103", "quantity": 12, "unit": "kg", "unit_cost": 45}, {"name": "Almonds", "lot": "AL-088", "quantity": 3, "unit": "kg", "unit_cost": 700}]}, "Batch costing and traceability"),
    product("fees", "Fees", "Make instalments and outstanding fees easy to follow.", "Coaching & tuition centres", "Revenue", [
        field("student", "Student reference or name"), field("course", "Course or batch"), money("fee", "Course fee · INR"),
        money("discount", "Agreed discount · INR"),
        rows("instalments", "Instalment schedule", [field("due", "Due date", "date"), money("amount", "Amount · INR")]),
        rows("payments", "Recorded payments", [field("reference", "Receipt reference"), field("date", "Payment date", "date"), money("amount", "Amount · INR")])
    ], {"student": "STU-0042", "course": "Foundation mathematics", "fee": 24000, "discount": 2000, "instalments": [{"due": future(-20), "amount": 11000}, {"due": future(20), "amount": 11000}], "payments": [{"reference": "R-001", "date": future(-18), "amount": 8000}]}, "Student fee statement"),
    product("renew", "Renew", "See the cancellation window before renewal arrives.", "Agencies & small companies", "Operations", [
        field("vendor", "Vendor"), field("service", "Subscription or contract"), field("owner", "Responsible person"),
        money("cost", "Cost per billing period · INR"), select("cadence", "Billing period", ["Monthly", "Quarterly", "Annual"]),
        field("renewal", "Next renewal date", "date"), integer("notice_days", "Cancellation notice days"),
        select("decision", "Renewal decision", ["Undecided", "Renew", "Cancel"])
    ], {"vendor": "Example Design Software", "service": "Team design subscription", "owner": "Operations lead", "cost": 3600, "cadence": "Monthly", "renewal": future(45), "notice_days": 30, "decision": "Undecided"}, "Renewal decision brief"),
    product("sop", "SOP", "Create clear procedures with a version to acknowledge.", "Frontline teams & growing businesses", "People", [
        field("procedure", "Procedure name"), field("owner", "Procedure owner"), integer("version", "Procedure version", min=1),
        field("steps", "Procedure steps · one per line", "textarea"),
        field("hazards", "Safety notes and escalation", "textarea", required=False),
        rows("acknowledgements", "Recorded acknowledgements", [field("employee", "Employee reference"), integer("version", "Acknowledged version", min=1)])
    ], {"procedure": "Open the service counter", "owner": "Shift supervisor", "version": 2, "steps": "Check the previous shift handover\nInspect equipment and report faults\nCount opening stock\nConfirm the team roster", "hazards": "Do not use damaged equipment. Escalate faults to the supervisor.", "acknowledgements": [{"employee": "TEAM-01", "version": 1}, {"employee": "TEAM-02", "version": 2}]}, "Versioned procedure checklist"),
    product("claimpack", "ClaimPack", "Organize the evidence behind a payment dispute.", "Small ecommerce brands", "Revenue", [
        field("order", "Order reference"), money("amount", "Disputed amount · INR"), field("deadline", "Response deadline", "date"),
        select("reason", "Dispute category", ["Not received", "Not as described", "Refund not received"]),
        field("summary", "Factual timeline", "textarea"),
        rows("evidence", "Evidence references · references only, no uploads yet", [select("kind", "Type", ["Order confirmation", "Delivery proof", "Customer communication", "Product description", "Refund proof"]), field("reference", "File or record reference")])
    ], {"order": "ORDER-1088", "amount": 2499, "deadline": future(7), "reason": "Not received", "summary": "Order placed on 12 October. Carrier reports delivery on 15 October. Customer contacted support on 17 October.", "evidence": [{"kind": "Order confirmation", "reference": "order-1088.pdf"}, {"kind": "Customer communication", "reference": "support-ticket-880"}]}, "Dispute evidence checklist")
]

CATALOG = {p["slug"]: p for p in PRODUCTS}
