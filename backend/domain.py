"""Deterministic, reviewable domain calculations. No external AI or side effects."""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from .catalog import CATALOG


class DomainError(ValueError):
    pass


def decimal(value):
    return Decimal(str(value))


def amount(value):
    return format(decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def lines(text):
    return [s.strip() for s in text.splitlines() if s.strip()]


def validate_fields(fields, data, prefix=""):
    if not isinstance(data, dict):
        raise DomainError("Expected an object")
    unknown = set(data) - {f["key"] for f in fields}
    if unknown:
        raise DomainError(f"Unknown fields: {', '.join(sorted(unknown))}")
    output = {}
    for f in fields:
        key, label, kind = f["key"], prefix + f["label"], f["type"]
        value = data.get(key)
        if value is None or value == "":
            if f.get("required", True):
                raise DomainError(f"{label} is required")
            output[key] = ""
            continue
        if kind == "rows":
            if not isinstance(value, list) or len(value) > 200:
                raise DomainError(f"{label} must have at most 200 rows")
            output[key] = [validate_fields(f["columns"], row, f"{label}, row {i + 1}: ") for i, row in enumerate(value)]
        elif kind == "number":
            try:
                n = decimal(value)
                if isinstance(value, bool) or not n.is_finite() or n < decimal(f.get("min", 0)) or n > decimal(f.get("max", 1e9)):
                    raise InvalidOperation
                if f.get("integer") and n != n.to_integral_value():
                    raise InvalidOperation
                if abs(n.as_tuple().exponent) > 6:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise DomainError(f"{label} must be a valid {'whole ' if f.get('integer') else ''}number between {f.get('min', 0)} and {f.get('max', 1e9)}")
            output[key] = str(int(n)) if f.get("integer") else str(n)
        else:
            if not isinstance(value, str) or len(value) > 20000:
                raise DomainError(f"{label} must be text of at most 20,000 characters")
            value = value.strip()
            if not value and f.get("required", True):
                raise DomainError(f"{label} is required")
            if kind == "select" and value not in f["options"]:
                raise DomainError(f"Invalid option for {label}")
            if kind == "date":
                try:
                    value = date.fromisoformat(value).isoformat()
                except ValueError:
                    raise DomainError(f"{label} must be a valid ISO date")
            output[key] = value
    return output


def calculate(slug, payload, today=None):
    if slug not in CATALOG:
        raise DomainError("Unknown product")
    p = validate_fields(CATALOG[slug]["fields"], payload)
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    metrics, items, warnings, blockers = {}, [], [], []
    heading, narrative = CATALOG[slug]["deliverable"], ""
    if slug == "scope":
        terms = set(re.findall(r"[a-z]{4,}", p["request"].lower()))
        for index, clause in enumerate(lines(p["baseline"]), 1):
            overlap = sorted(terms & set(re.findall(r"[a-z]{4,}", clause.lower())))
            items.append({"Clause": index, "Agreed deliverable": clause, "Shared terms": ", ".join(overlap) or "None"})
        metrics = {"Estimated change · INR": amount(decimal(p["hours"]) * decimal(p["rate"])), "Additional days": p["extra_days"], "Assessment": p["decision"]}
        if p["decision"] in ("Unreviewed", "Needs clarification"):
            blockers.append("Record your scope assessment before marking this reviewed.")
        warnings.append("Shared terms are a text-matching aid. They do not establish whether work is contractually in scope.")
        narrative = f"Client: {p['client']}\nRequested work: {p['request']}\nAssessment: {p['decision']}\nEstimated effort: {p['hours']} hours at INR {amount(p['rate'])}/hour.\nAdditional delivery time: {p['extra_days']} days.\nThis is an internal draft; customer approval has not been recorded."
    elif slug == "collect":
        balance = decimal(p["amount"]) - decimal(p["paid"])
        if balance < 0:
            raise DomainError("Recorded payments cannot exceed the invoice amount in this first workflow")
        overdue = max(0, (today - date.fromisoformat(p["due"])).days)
        if balance == 0:
            action = "Paid · stop follow-up"
        elif p["disputed"] == "Yes":
            action = "Resolve dispute · pause payment reminders"
        elif p["promise"] and date.fromisoformat(p["promise"]) >= today:
            action = "Wait for promised payment"
        elif p["promise"]:
            action = "Follow up on broken promise"
        elif overdue:
            action = "Follow up on overdue payment"
        else:
            action = "Not yet due"
        metrics = {"Outstanding · INR": amount(balance), "Days overdue": overdue if balance else 0, "Next action": action}
        narrative = f"{p['customer']} · {p['invoice']}\nOriginal amount: INR {amount(p['amount'])}\nRecorded paid: INR {amount(p['paid'])}\nBalance: INR {amount(balance)}\nNext action: {action}\nNotes: {p['notes'] or 'None'}"
        warnings.append("Payment amounts are manually recorded. No gateway reconciliation or messages are active.")
    elif slug == "amc":
        if date.fromisoformat(p["start"]) > date.fromisoformat(p["end"]):
            raise DomainError("Contract expiry must be on or after the start date")
        remaining = int(p["included"]) - int(p["completed"])
        if remaining < 0:
            raise DomainError("Completed visits exceed entitlement; extra visits require a separate chargeable visit record")
        days = (date.fromisoformat(p["end"]) - today).days
        state = "Expired" if days < 0 else "Not yet active" if date.fromisoformat(p["start"]) > today else "Renewal due" if days <= 30 else "Active"
        if p["next_visit"] and not (p["start"] <= p["next_visit"] <= p["end"]):
            blockers.append("Next service date must fall within the contract period.")
        if p["next_visit"] and not remaining:
            blockers.append("No included visits remain for the next service.")
        metrics = {"Contract": state, "Included visits left": remaining, "Days to expiry": days}
        items = [{"Equipment": p["asset"], "Customer": p["customer"], "Next visit": p["next_visit"] or "Unscheduled", "Contract value · INR": amount(p["contract_value"])}]
        narrative = "Visit completion and entitlement are manually maintained in this first workflow."
    elif slug == "rfq":
        if len(p["quotes"]) < 2:
            raise DomainError("Add at least two supplier quotations to compare")
        seen = set()
        for q in p["quotes"]:
            key = q["supplier"].casefold()
            if key in seen:
                raise DomainError("Supplier names must be unique within a comparison")
            seen.add(key)
            goods = decimal(q["unit_price"]) * int(p["quantity"])
            tax = goods * decimal(q["tax_percent"]) / 100
            total = goods + tax + decimal(q["freight"])
            items.append({"Supplier": q["supplier"], "Goods · INR": amount(goods), "Tax · INR": amount(tax), "Freight · INR": amount(q["freight"]), "Total · INR": amount(total), "Lead days": int(q["lead_days"]), "Exclusions": q["exclusions"] or "None stated"})
        items.sort(key=lambda q: decimal(q["Total · INR"]))
        metrics = {"Lowest total · INR": items[0]["Total · INR"], "Suppliers": len(items), "Required units": p["quantity"]}
        warnings.append("Comparison assumes INR, equal specifications, tax on goods only, and freight already inclusive of applicable charges. Confirm exclusions before selecting a supplier.")
        narrative = f"Specification: {p['item']}. Ranking is by calculated total only; no supplier has been awarded work."
    elif slug == "tender":
        available = {s.casefold() for s in lines(p["available"])}
        for index, raw in enumerate(p["source"].splitlines(), 1):
            if re.search(r"\b(required|must|shall|mandatory)\b", raw, re.I):
                requirement = re.sub(r"^\s*(?:required|must provide|mandatory)\s*:\s*", "", raw, flags=re.I).strip()
                items.append({"Source line": index, "Requirement": requirement, "Document": "Listed as available" if requirement.casefold() in available else "Needs review / evidence"})
        missing = sum(i["Document"] != "Listed as available" for i in items)
        if not items:
            blockers.append("No explicit requirement markers found. Add marked requirement lines or review the source manually.")
        if missing:
            blockers.append(f"{missing} requirement(s) need evidence or manual resolution.")
        if date.fromisoformat(p["deadline"]) < today:
            blockers.append("The entered submission date has passed.")
        metrics = {"Requirements found": len(items), "Need evidence": missing, "Days to deadline": (date.fromisoformat(p["deadline"]) - today).days}
        warnings.append("Only explicit requirement lines in pasted text are detected. This is not a complete tender interpretation or eligibility determination; uploaded documents are not verified.")
        narrative = f"Buyer: {p['authority']}\nEntered deadline: {p['deadline']}\nReview the complete tender and any amendments before submission."
    elif slug == "handover":
        if not p["issues"]:
            raise DomainError("Add at least one inspection item")
        outstanding = [i for i in p["issues"] if i["status"] != "Verified"]
        critical = sum(i["severity"] == "Critical" for i in outstanding)
        metrics = {"Inspection items": len(p["issues"]), "Awaiting verification": len(outstanding), "Critical outstanding": critical}
        if outstanding:
            blockers.append("Every inspection item must be verified before the handover checklist can be marked reviewed.")
        items = [{"Area": i["room"], "Issue": i["description"], "Severity": i["severity"], "Assigned to": i["assignee"], "Status": i["status"]} for i in p["issues"]]
        narrative = f"{p['site']} · {p['client']}\nChecklist review does not record customer acceptance or a signature."
    elif slug == "orderdesk":
        if not p["catalog"]:
            raise DomainError("Add catalogue items before checking the order")
        skus = [c["sku"].casefold() for c in p["catalog"]]
        if len(skus) != len(set(skus)):
            raise DomainError("Catalogue SKUs must be unique")
        total, demand = Decimal(0), {}
        for raw in lines(p["order_text"]):
            match = re.fullmatch(r"(\d+)\s*[x×]\s*(.+)", raw, flags=re.I)
            if not match or int(match[1]) < 1 or int(match[1]) > 1_000_000:
                items.append({"Requested line": raw, "Status": "Clarify quantity and SKU", "Quantity": "", "SKU": "", "Line total · INR": ""})
                blockers.append(f"Clarify order line: {raw}")
                continue
            quantity, name = int(match[1]), match[2].strip().casefold()
            matches = [c for c in p["catalog"] if name in (c["sku"].casefold(), c["name"].casefold())]
            if len(matches) != 1:
                items.append({"Requested line": raw, "Status": "Ambiguous / unknown item", "Quantity": quantity, "SKU": "", "Line total · INR": ""})
                blockers.append(f"Choose one exact catalogue item for: {raw}")
                continue
            c = matches[0]
            demand[c["sku"]] = demand.get(c["sku"], 0) + quantity
            value = decimal(c["price"]) * quantity
            total += value
            items.append({"Requested line": raw, "Status": "Matched", "Quantity": quantity, "SKU": c["sku"], "Line total · INR": amount(value)})
        for c in p["catalog"]:
            if demand.get(c["sku"], 0) > int(c["stock"]):
                blockers.append(f"Combined quantity for {c['sku']} exceeds available stock.")
        metrics = {"Matched subtotal · INR": amount(total), "Order lines": len(items), "Issues": len(blockers)}
        narrative = f"Customer: {p['customer']}. This is a draft. Stock has not been reserved; taxes and shipping are not included."
    elif slug == "batch":
        if not p["ingredients"]:
            raise DomainError("Add at least one consumed ingredient lot")
        total = decimal(p["overhead"])
        for i in p["ingredients"]:
            value = decimal(i["quantity"]) * decimal(i["unit_cost"])
            total += value
            items.append({"Ingredient": i["name"], "Supplier lot": i["lot"], "Consumed": f"{i['quantity']} {i['unit']}", "Cost · INR": amount(value)})
        metrics = {"Total batch cost · INR": amount(total), "Cost per finished unit · INR": amount(total / int(p["produced_units"])), "Output attainment %": amount(100 * decimal(p["produced_units"]) / decimal(p["planned_units"]))}
        if date.fromisoformat(p["expiry"]) < today:
            blockers.append("Finished batch expiry is in the past.")
        narrative = f"Batch {p['batch_number']} · {p['product']}\nExpiry: {p['expiry']}\nActual output: {p['produced_units']} units. Output attainment compares finished units to plan, not ingredient mass yield."
        warnings.append("Inventory movements, production release, and recall execution are not connected.")
    elif slug == "fees":
        net = decimal(p["fee"]) - decimal(p["discount"])
        if net < 0:
            raise DomainError("Discount cannot exceed the course fee")
        scheduled = sum((decimal(i["amount"]) for i in p["instalments"]), Decimal(0))
        if scheduled != net:
            raise DomainError("Instalment amounts must add up to the fee after discount")
        references = [r["reference"].casefold() for r in p["payments"]]
        if len(references) != len(set(references)):
            raise DomainError("Payment receipt references must be unique")
        if any(date.fromisoformat(r["date"]) > today for r in p["payments"]):
            raise DomainError("Recorded payments cannot have future dates")
        paid = sum((decimal(r["amount"]) for r in p["payments"]), Decimal(0))
        if paid > net:
            raise DomainError("Recorded payments cannot exceed the net fee")
        due = sum((decimal(i["amount"]) for i in p["instalments"] if date.fromisoformat(i["due"]) <= today), Decimal(0))
        credit = paid
        for i in sorted(p["instalments"], key=lambda r: r["due"]):
            applied = min(credit, decimal(i["amount"]))
            credit -= applied
            items.append({"Due date": i["due"], "Amount · INR": amount(i["amount"]), "Applied · INR": amount(applied), "Balance · INR": amount(decimal(i["amount"]) - applied)})
        metrics = {"Net fee · INR": amount(net), "Outstanding · INR": amount(net - paid), "Due now · INR": amount(max(Decimal(0), due - paid))}
        narrative = f"Student: {p['student']}\nCourse: {p['course']}\nPayments are allocated to the oldest instalment first. Receipt references are manual records, not verified payment confirmations."
    elif slug == "renew":
        renewal = date.fromisoformat(p["renewal"])
        notice = renewal - timedelta(days=int(p["notice_days"]))
        annual = decimal(p["cost"]) * {"Monthly": 12, "Quarterly": 4, "Annual": 1}[p["cadence"]]
        metrics = {"Annualized cost · INR": amount(annual), "Notice deadline": notice.isoformat(), "Days to notice": (notice - today).days}
        if p["decision"] == "Undecided":
            blockers.append("Record a renewal decision before marking reviewed.")
        if notice < today:
            warnings.append("The entered notice window has passed. Check the contract for available options.")
        narrative = f"Vendor: {p['vendor']}\nService: {p['service']}\nOwner: {p['owner']}\nDecision: {p['decision']}\nNo vendor cancellation or renewal has been submitted."
    elif slug == "sop":
        steps = lines(p["steps"])
        if len(steps) < 2:
            raise DomainError("Add at least two clear procedure steps")
        employees = [a["employee"].casefold() for a in p["acknowledgements"]]
        if len(employees) != len(set(employees)):
            raise DomainError("An employee may have only one recorded acknowledgement per procedure")
        if any(int(a["version"]) > int(p["version"]) for a in p["acknowledgements"]):
            raise DomainError("Acknowledgement version cannot be newer than the procedure")
        current = sum(a["version"] == p["version"] for a in p["acknowledgements"])
        metrics = {"Procedure version": p["version"], "Steps": len(steps), "Current acknowledgements": f"{current} / {len(p['acknowledgements'])}"}
        items = [{"Step": n, "Instruction": text} for n, text in enumerate(steps, 1)]
        narrative = f"{p['procedure']} · version {p['version']}\nOwner: {p['owner']}\nSafety and escalation: {p['hazards'] or 'Not provided'}"
        warnings.append("Acknowledgements are manually recorded; employee identity and training assessments are not verified.")
    elif slug == "claimpack":
        required = {"Order confirmation", "Customer communication", {"Not received": "Delivery proof", "Not as described": "Product description", "Refund not received": "Refund proof"}[p["reason"]]}
        provided = {e["kind"] for e in p["evidence"]}
        missing = sorted(required - provided)
        if missing:
            blockers.append("Missing references: " + ", ".join(missing))
        days = (date.fromisoformat(p["deadline"]) - today).days
        if days < 0:
            blockers.append("Entered response deadline has passed.")
        metrics = {"Disputed · INR": amount(p["amount"]), "Missing reference types": len(missing), "Days to respond": days}
        items = [{"Evidence type": e["kind"], "Reference": e["reference"]} for e in p["evidence"]]
        narrative = f"Order: {p['order']}\nDispute: {p['reason']}\nTimeline: {p['summary']}"
        warnings.append("Checklist requirements are an internal preparation template. File contents are not uploaded or verified, and nothing is submitted to a payment provider.")
    return p, {"heading": heading, "as_of": today.isoformat(), "metrics": metrics, "items": items,
               "narrative": narrative, "warnings": warnings, "blockers": blockers, "can_review": not blockers}
