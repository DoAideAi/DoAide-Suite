from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import pytest
from backend.catalog import PRODUCTS, CATALOG
from backend.domain import calculate, DomainError


def sample(slug, **updates):
    return {**deepcopy(CATALOG[slug]["sample"]), **updates}


@pytest.mark.parametrize("product", PRODUCTS, ids=lambda p: p["slug"])
def test_each_product_has_meaningful_result(product):
    _, result = calculate(product["slug"], product["sample"])
    assert result["metrics"]
    assert result["heading"] == product["deliverable"]
    assert result["can_review"] == (not result["blockers"])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "-1", True, "1e100", "0.123456789"])
def test_money_inputs_reject_unsafe_numeric_values(value):
    with pytest.raises(DomainError):
        calculate("scope", sample("scope", rate=value))


def test_scope_estimate_is_exact_and_requires_human_assessment():
    _, r = calculate("scope", sample("scope", hours="0.1", rate="0.2"))
    assert r["metrics"]["Estimated change · INR"] == "0.02"
    assert not r["can_review"]
    _, r = calculate("scope", sample("scope", decision="Change required"))
    assert r["can_review"] and r["metrics"]["Estimated change · INR"] == "36000.00"


@pytest.mark.parametrize("updates, action", [
    ({"paid":85000, "disputed":"Yes"}, "Paid · stop follow-up"),
    ({"disputed":"Yes"}, "Resolve dispute · pause payment reminders"),
    ({"promise":"2026-10-29"}, "Wait for promised payment"),
    ({"promise":"2026-10-26"}, "Follow up on broken promise"),
    ({"promise":"", "due":"2026-10-20"}, "Follow up on overdue payment"),
    ({"promise":"", "due":"2026-10-28"}, "Not yet due"),
])
def test_collection_priority(updates, action):
    _, r = calculate("collect", sample("collect", **updates), date(2026,10,27))
    assert r["metrics"]["Next action"] == action


def test_overpayment_rejected():
    with pytest.raises(DomainError, match="exceed"):
        calculate("collect", sample("collect", paid=85001))


def test_amc_period_and_entitlement():
    with pytest.raises(DomainError, match="expiry"):
        calculate("amc", sample("amc", start="2027-01-01", end="2026-01-01"))
    with pytest.raises(DomainError, match="entitlement"):
        calculate("amc", sample("amc", completed=5))
    _, r = calculate("amc", sample("amc", completed=4))
    assert not r["can_review"]


def test_integer_input_from_decimal_is_normalized():
    p, r = calculate("amc", sample("amc", included="4.0"))
    assert p["included"] == "4"
    assert r["metrics"]["Included visits left"] == 1


def test_rfq_arithmetic_and_ordering():
    _, r = calculate("rfq", sample("rfq"))
    assert r["items"][0]["Supplier"] == "Atlas Metals"
    assert r["items"][0]["Total · INR"] == "93250.00"
    assert r["items"][1]["Total · INR"] == "95580.00"


def test_rfq_duplicate_supplier_is_not_a_comparison():
    p = sample("rfq"); p["quotes"][1]["supplier"] = "atlas metals"
    with pytest.raises(DomainError, match="unique"):
        calculate("rfq", p)


def test_tender_citations_preserve_original_line_numbers():
    p = sample("tender", source="Introduction\n\nRequired: certificate\nInformation", available="certificate", deadline="2027-01-01")
    _, r = calculate("tender", p, date(2026,10,27))
    assert r["items"] == [{"Source line":3, "Requirement":"certificate", "Document":"Listed as available"}]
    assert r["can_review"]


def test_tender_without_requirements_does_not_claim_ready():
    _, r = calculate("tender", sample("tender", source="General information"))
    assert not r["can_review"]


def test_handover_requires_verification_not_just_fixed():
    p = sample("handover")
    for issue in p["issues"]: issue["status"] = "Fixed"
    assert not calculate("handover", p)[1]["can_review"]
    for issue in p["issues"]: issue["status"] = "Verified"
    assert calculate("handover", p)[1]["can_review"]


@pytest.mark.parametrize("text", ["TEA-250", "0 x TEA-250", "2 x Unknown", "1.5 x TEA-250", "-2 x TEA-250"])
def test_orderdesk_does_not_guess(text):
    assert not calculate("orderdesk", sample("orderdesk", order_text=text))[1]["can_review"]


def test_orderdesk_aggregates_duplicate_lines_for_stock():
    _, r = calculate("orderdesk", sample("orderdesk", order_text="25 x TEA-250\n20 x TEA-250"))
    assert "Combined quantity" in r["blockers"][0]


def test_orderdesk_ambiguous_names_need_clarification():
    p = sample("orderdesk", order_text="2 x Tea 250g")
    p["catalog"].append({"sku":"TEA-OTHER", "name":"Tea 250g", "price":99, "stock":100})
    assert not calculate("orderdesk", p)[1]["can_review"]


def test_batch_cost_and_attainment_are_distinct():
    _, r = calculate("batch", sample("batch"))
    assert r["metrics"] == {"Total batch cost · INR":"3540.00", "Cost per finished unit · INR":"38.48", "Output attainment %":"92.00"}


def test_batch_zero_output_cannot_divide_by_zero():
    with pytest.raises(DomainError):
        calculate("batch", sample("batch", produced_units=0))


def test_fees_payment_allocation_and_overdue():
    _, r = calculate("fees", sample("fees"))
    assert r["metrics"]["Outstanding · INR"] == "14000.00"
    assert r["metrics"]["Due now · INR"] == "3000.00"
    assert r["items"][0]["Applied · INR"] == "8000.00"
    assert r["items"][1]["Applied · INR"] == "0.00"


def test_fees_rejects_duplicate_receipts_and_bad_schedule():
    p = sample("fees"); p["payments"].append(p["payments"][0].copy())
    with pytest.raises(DomainError, match="unique"): calculate("fees", p)
    with pytest.raises(DomainError, match="add up"): calculate("fees", sample("fees", discount=3000))


def test_fees_rejects_future_payment_date():
    p = sample("fees"); p["payments"][0]["date"] = "2026-10-28"
    with pytest.raises(DomainError, match="future"): calculate("fees", p, date(2026,10,27))


def test_renew_handles_year_boundary():
    _, r = calculate("renew", sample("renew", renewal="2027-01-10", notice_days=30, decision="Cancel"), date(2026,12,1))
    assert r["metrics"]["Notice deadline"] == "2026-12-11"
    assert r["metrics"]["Annualized cost · INR"] == "43200.00"
    assert r["can_review"]
    assert "No vendor cancellation" in r["narrative"]


def test_sop_marks_old_acknowledgements_as_stale():
    _, r = calculate("sop", sample("sop"))
    assert r["metrics"]["Current acknowledgements"] == "1 / 2"


def test_sop_rejects_future_acknowledgement():
    p = sample("sop"); p["acknowledgements"][0]["version"] = 3
    with pytest.raises(DomainError, match="newer"): calculate("sop", p)


def test_claimpack_missing_delivery_evidence_and_deadline():
    _, r = calculate("claimpack", sample("claimpack", deadline="2026-10-26"), date(2026,10,27))
    assert len(r["blockers"]) == 2
    assert "Delivery proof" in r["blockers"][0]


@pytest.mark.parametrize("slug, changes", [
    ("scope", {"client":"  "}), ("scope", {"decision":"Approve"}),
    ("collect", {"due":"2026-02-30"}), ("amc", {"included":"2.5"}),
    ("scope", {"admin":True}), ("rfq", {"quotes":[]})
])
def test_invalid_contracts_rejected(slug, changes):
    with pytest.raises(DomainError): calculate(slug, sample(slug, **changes))
