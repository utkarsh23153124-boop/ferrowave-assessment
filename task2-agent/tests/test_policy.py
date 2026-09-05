"""Policy rules, tested without a network or a model.

Each case names the clause of `corpus/policies/refund-policy.md` it pins down. These run
in milliseconds and are the tests to read first when arguing that policy is enforced by
code.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from billing.policy import (ANNUAL_WINDOW_DAYS, MONTHLY_NEW_WINDOW_DAYS, cap_refund_amount,
                            evaluate_plan_change, evaluate_refund)

NOW = datetime(2026, 8, 29, 9, 0, 0, tzinfo=timezone.utc)


def invoice(days_ago, kind="new_subscription", amount=9900, refunded=0,
            status="paid", lines=None):
    issued = NOW.timestamp() - days_ago * 86400
    return {
        "id": "inv_test", "number": "FW-TEST", "kind": kind, "amount_minor": amount,
        "refunded_minor": refunded, "status": status, "currency": "USD",
        "issued_at": datetime.fromtimestamp(issued, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "line_items": lines if lines is not None else [
            {"description": "Growth plan (monthly)", "amount_minor": amount}],
    }


def sub(plan="growth", cycle="monthly", seats_used=4, seats_included=10):
    return {"id": "sub_test", "plan": plan, "billing_cycle": cycle,
            "seats_used": seats_used, "seats_included": seats_included,
            "price_minor": 9900, "currency": "USD"}


# --- 1.1 monthly new subscriptions, 14 days ---------------------------------
@pytest.mark.parametrize("days,allowed", [(0, True), (13, True), (14, True), (15, False), (40, False)])
def test_monthly_new_window_boundary(days, allowed):
    d = evaluate_refund(invoice(days), sub(), NOW)
    assert d.allowed is allowed
    if allowed:
        assert d.max_amount_minor == 9900


def test_monthly_new_window_is_fourteen_not_thirty():
    """The PM spec claims 30 days on all plans; the policy says 14 for monthly.

    Documented in DECISIONS.md under Spec issues. This test is what stops the spec's
    number from creeping back in.
    """
    assert MONTHLY_NEW_WINDOW_DAYS == 14
    assert evaluate_refund(invoice(20), sub(), NOW).allowed is False


# --- 1.2 monthly renewals ---------------------------------------------------
def test_monthly_renewal_never_refundable():
    d = evaluate_refund(invoice(2, kind="renewal"), sub(), NOW)
    assert d.allowed is False
    assert d.code == "monthly_renewal_not_refundable"
    assert "Refund Policy 1.2" in d.cites


# --- 1.3 overage ------------------------------------------------------------
def test_overage_never_refundable():
    d = evaluate_refund(invoice(1, kind="overage"), sub(), NOW)
    assert d.allowed is False and d.code == "overage_not_refundable"


# --- 1.4 seat reversal within 24 hours --------------------------------------
SEAT_INVOICE_LINES = [
    {"description": "Growth plan (monthly)", "amount_minor": 9900},
    {"description": "3 additional seat(s) (monthly)", "amount_minor": 2700},
]


def test_seat_reversal_refunds_only_the_seat_lines():
    inv = invoice(2, kind="renewal", amount=12600, lines=SEAT_INVOICE_LINES)
    d = evaluate_refund(inv, sub(), NOW, seat_reversal_claimed=True)
    assert d.allowed is True
    assert d.max_amount_minor == 2700, "the 9900 plan fee must not be refundable"
    assert d.needs_human_evidence is True


def test_seat_reversal_requires_the_claim():
    """Without the customer's account of events the renewal rule applies unchanged."""
    inv = invoice(2, kind="renewal", amount=12600, lines=SEAT_INVOICE_LINES)
    assert evaluate_refund(inv, sub(), NOW).allowed is False


# --- 2.1 / 2.2 annual -------------------------------------------------------
@pytest.mark.parametrize("days,allowed", [(0, True), (30, True), (31, False)])
def test_annual_window_boundary(days, allowed):
    d = evaluate_refund(invoice(days, amount=29000), sub(cycle="annual"), NOW)
    assert d.allowed is allowed


def test_annual_renewals_are_refundable_unlike_monthly():
    """2.1 covers 'new subscriptions and renewals'; 1.2 excludes monthly renewals."""
    assert evaluate_refund(invoice(5, kind="renewal"), sub(cycle="annual"), NOW).allowed is True
    assert evaluate_refund(invoice(5, kind="renewal"), sub(cycle="monthly"), NOW).allowed is False


# --- 3 enterprise -----------------------------------------------------------
def test_enterprise_is_never_self_serve_refundable():
    d = evaluate_refund(invoice(1), sub(plan="enterprise"), NOW)
    assert d.allowed is False and d.code == "enterprise_contract"


# --- invoice state ----------------------------------------------------------
def test_already_refunded_invoice():
    d = evaluate_refund(invoice(1, refunded=9900, status="refunded"), sub(), NOW)
    assert d.allowed is False


def test_partially_refunded_invoice_caps_at_the_remainder():
    d = evaluate_refund(invoice(1, refunded=4000, status="partially_refunded"), sub(), NOW)
    assert d.allowed is True and d.max_amount_minor == 5900


def test_open_invoice_cannot_be_refunded():
    assert evaluate_refund(invoice(1, status="open"), sub(), NOW).allowed is False


# --- amount capping ---------------------------------------------------------
def test_cap_never_widens_a_decision():
    denied = evaluate_refund(invoice(40), sub(), NOW)
    assert cap_refund_amount(denied, 9900) == 0


def test_cap_clamps_an_over_request():
    allowed = evaluate_refund(invoice(1), sub(), NOW)
    assert cap_refund_amount(allowed, 999999) == 9900
    assert cap_refund_amount(allowed, 5000) == 5000
    assert cap_refund_amount(allowed, None) == 9900
    assert cap_refund_amount(allowed, -5) == 0


# --- plan changes -----------------------------------------------------------
def test_downgrade_is_next_cycle_only():
    """PM spec point 5 asks for immediate downgrades; the billing system refuses them."""
    d = evaluate_plan_change(sub(plan="scale", seats_used=4), "growth")
    assert d.allowed is True and d.effective == "next_cycle"


def test_downgrade_blocked_by_seat_limit():
    d = evaluate_plan_change(sub(plan="growth", seats_used=12), "starter")
    assert d.allowed is False and d.code == "seat_limit_exceeded"


def test_upgrade_can_be_immediate():
    d = evaluate_plan_change(sub(plan="starter", seats_used=2), "growth")
    assert d.allowed is True and d.direction == "upgrade" and d.effective == "now"


def test_enterprise_plan_change_refused():
    d = evaluate_plan_change(sub(plan="enterprise"), "scale")
    assert d.allowed is False and d.code == "enterprise_plan_restriction"


def test_same_plan_is_rejected_before_it_reaches_the_api():
    assert evaluate_plan_change(sub(), "growth", "monthly").code == "already_on_plan"


def test_cycle_change_is_treated_as_an_upgrade_path():
    d = evaluate_plan_change(sub(), "growth", "annual")
    assert d.allowed is True and d.direction == "cycle_change"


def test_unknown_plan_rejected():
    assert evaluate_plan_change(sub(), "platinum").allowed is False
