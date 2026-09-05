"""Ferrowave refund and plan-change policy, enforced in code.

Every rule here is a transcription of a clause in `corpus/policies/refund-policy.md`
(Version 3, approved 10 February 2026) or a constraint documented in
`sandbox/API_REFERENCE.md`. The language model never decides whether money may move; it
may only ask this module and report what it says.

Clause references in `cites` are used in customer-facing explanations, so a customer can
always be told which rule produced the outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# --- Refund policy constants -------------------------------------------------
# refund-policy.md 1.1: monthly new subscriptions, full refund within 14 days.
MONTHLY_NEW_WINDOW_DAYS = 14
# refund-policy.md 2.1: annual charges, prorated refund within 30 days.
ANNUAL_WINDOW_DAYS = 30
# refund-policy.md 1.4: seats added and removed within 24 hours are refunded in full.
SEAT_REVERSAL_WINDOW_HOURS = 24

REFUNDABLE_INVOICE_STATUSES = ("paid", "partially_refunded")

# Invoice kinds, from API_REFERENCE.md.
KIND_NEW = "new_subscription"
KIND_RENEWAL = "renewal"
KIND_OVERAGE = "overage"
KIND_SEAT_CHANGE = "seat_change"
KIND_ADDON = "addon"


@dataclass
class RefundDecision:
    """The outcome of applying the Refund Policy to one invoice."""

    allowed: bool
    max_amount_minor: int
    code: str
    explanation: str
    cites: list = field(default_factory=list)
    # True when policy permits a refund only if a fact the API cannot confirm is true.
    # The agent must route these to a human instead of deciding on its own.
    needs_human_evidence: bool = False

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "max_amount_minor": self.max_amount_minor,
            "code": self.code,
            "explanation": self.explanation,
            "cites": list(self.cites),
            "needs_human_evidence": self.needs_human_evidence,
        }


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _seat_line_total_minor(invoice: dict) -> int:
    """Minor units on this invoice attributable to additional seats.

    The sandbox describes them as "N additional seat(s) (monthly)"; anything mentioning
    seats counts as a seat line, so a wording change cannot silently refund a plan fee.
    """
    total = 0
    for item in invoice.get("line_items") or []:
        if "seat" in (item.get("description") or "").lower():
            total += int(item.get("amount_minor") or 0)
    return total


def evaluate_refund(
    invoice: dict,
    subscription: dict,
    now: datetime,
    seat_reversal_claimed: bool = False,
) -> RefundDecision:
    """Decide whether `invoice` may be refunded, and at most how much.

    `now` must be the sandbox clock (X-Sandbox-Now), never the local machine clock.
    `seat_reversal_claimed` records that the customer says they added seats and removed
    them within 24 hours; it never by itself authorises money to move.
    """
    refundable_minor = int(invoice["amount_minor"]) - int(invoice.get("refunded_minor") or 0)
    label = invoice.get("number") or invoice["id"]

    # State checks first: a policy verdict on an unpayable invoice is meaningless.
    if invoice.get("status") not in REFUNDABLE_INVOICE_STATUSES:
        return RefundDecision(
            False, 0, "invoice_not_refundable",
            "Invoice {} has status '{}', so there is nothing to refund on it.".format(
                label, invoice.get("status")),
        )
    if refundable_minor <= 0:
        return RefundDecision(
            False, 0, "already_fully_refunded",
            "Invoice {} has already been refunded in full.".format(label),
        )

    plan = (subscription.get("plan") or "").lower()
    cycle = (subscription.get("billing_cycle") or "").lower()
    kind = invoice.get("kind")
    days = (now - _parse(invoice["issued_at"])).days

    # refund-policy.md 3: Enterprise is contractual, never self-serve.
    if plan == "enterprise":
        return RefundDecision(
            False, 0, "enterprise_contract",
            "Enterprise fees are governed by the contract and are not refunded through "
            "self-serve support. Your account manager handles this.",
            ["Refund Policy 3"],
        )

    # refund-policy.md 1.3: overage is never refundable.
    if kind == KIND_OVERAGE:
        return RefundDecision(
            False, 0, "overage_not_refundable",
            "Overage charges are not refundable under the Refund Policy.",
            ["Refund Policy 1.3"],
        )

    if cycle == "annual":
        # refund-policy.md 2.1: new subscriptions and renewals, prorated, within 30 days.
        if days <= ANNUAL_WINDOW_DAYS:
            return RefundDecision(
                True, refundable_minor, "annual_within_window",
                "This annual charge was issued {} day(s) ago, inside the {}-day window, "
                "so a prorated refund of the unused portion is available.".format(
                    days, ANNUAL_WINDOW_DAYS),
                ["Refund Policy 2.1"],
            )
        return RefundDecision(
            False, 0, "annual_window_expired",
            "This annual charge was issued {} days ago, past the {}-day refund window. "
            "You can still cancel to stop the next renewal.".format(days, ANNUAL_WINDOW_DAYS),
            ["Refund Policy 2.2"],
        )

    # --- monthly ---
    if kind == KIND_NEW:
        # refund-policy.md 1.1: full refund of the first month within 14 days.
        if days <= MONTHLY_NEW_WINDOW_DAYS:
            return RefundDecision(
                True, refundable_minor, "monthly_new_within_window",
                "This first monthly charge was issued {} day(s) ago, inside the {}-day "
                "window, so a full refund is available.".format(days, MONTHLY_NEW_WINDOW_DAYS),
                ["Refund Policy 1.1"],
            )
        return RefundDecision(
            False, 0, "monthly_new_window_expired",
            "This charge was issued {} days ago, past the {}-day window for a first "
            "monthly subscription.".format(days, MONTHLY_NEW_WINDOW_DAYS),
            ["Refund Policy 1.1"],
        )

    # refund-policy.md 1.4 sits inside 1.2: the plan fee on a renewal is not refundable,
    # but a seat charge reversed within 24 hours is. Only the seat lines may move, and
    # only a human can confirm the removal happened inside the window.
    seat_minor = _seat_line_total_minor(invoice)
    if kind in (KIND_RENEWAL, KIND_SEAT_CHANGE) and seat_minor > 0 and seat_reversal_claimed:
        return RefundDecision(
            True, min(seat_minor, refundable_minor), "seat_reversal_within_24h",
            "Seats added and removed within {} hours are refunded in full, so the seat "
            "charge on this invoice can be returned. The plan fee itself stays, because "
            "monthly renewals are not refundable.".format(SEAT_REVERSAL_WINDOW_HOURS),
            ["Refund Policy 1.4", "Refund Policy 1.2"],
            needs_human_evidence=True,
        )

    if kind == KIND_RENEWAL:
        return RefundDecision(
            False, 0, "monthly_renewal_not_refundable",
            "Monthly renewal charges are not refundable. You can cancel at any time and "
            "the subscription stays active until the end of the paid period.",
            ["Refund Policy 1.2"],
        )

    return RefundDecision(
        False, 0, "no_rule_permits",
        "The Refund Policy does not provide for a refund of this charge. A member of the "
        "billing team can look at it with you.",
        ["Refund Policy 1", "Refund Policy 2"],
    )


def cap_refund_amount(decision: RefundDecision, requested_minor: Optional[int]) -> int:
    """Clamp a requested amount to what policy allows. Never widens a decision."""
    if not decision.allowed:
        return 0
    if requested_minor is None:
        return decision.max_amount_minor
    return max(0, min(int(requested_minor), decision.max_amount_minor))


# --- Plan changes ------------------------------------------------------------
SELF_SERVE_PLANS = ("starter", "growth", "scale")
PLAN_RANK = {"starter": 1, "growth": 2, "scale": 3, "enterprise": 4}
SEATS_INCLUDED = {"starter": 3, "growth": 10, "scale": 25, "enterprise": 100}


@dataclass
class PlanChangeDecision:
    allowed: bool
    direction: str
    effective: str
    code: str
    explanation: str
    cites: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed, "direction": self.direction,
            "effective": self.effective, "code": self.code,
            "explanation": self.explanation, "cites": list(self.cites),
        }


def evaluate_plan_change(
    subscription: dict,
    target_plan: str,
    target_cycle: Optional[str] = None,
) -> PlanChangeDecision:
    """Decide the direction and the legal effective date of a plan change.

    Mirrors the rules the sandbox enforces (API_REFERENCE.md, POST
    /subscriptions/{id}/change) so the agent never promises a change the billing system
    will then reject.
    """
    plan = (subscription.get("plan") or "").lower()
    cycle = (subscription.get("billing_cycle") or "").lower()
    target_plan = (target_plan or "").lower()
    target_cycle = (target_cycle or cycle).lower()

    if plan == "enterprise":
        return PlanChangeDecision(
            False, "none", "none", "enterprise_plan_restriction",
            "Enterprise subscriptions are changed by your account manager, not through "
            "self-serve billing.", ["API_REFERENCE plan_restriction"],
        )
    if target_plan not in SELF_SERVE_PLANS:
        return PlanChangeDecision(
            False, "none", "none", "unknown_plan",
            "'{}' is not a self-serve plan. The self-serve plans are {}.".format(
                target_plan, ", ".join(SELF_SERVE_PLANS)), [],
        )
    if target_plan == plan and target_cycle == cycle:
        return PlanChangeDecision(
            False, "same", "none", "already_on_plan",
            "The subscription is already on {} billed {}.".format(plan, cycle), [],
        )

    if target_plan == plan:
        direction = "cycle_change"
    else:
        direction = "upgrade" if PLAN_RANK[target_plan] > PLAN_RANK[plan] else "downgrade"

    if direction == "downgrade":
        seats_used = int(subscription.get("seats_used") or 0)
        allowed_seats = SEATS_INCLUDED[target_plan]
        if seats_used > allowed_seats:
            return PlanChangeDecision(
                False, direction, "next_cycle", "seat_limit_exceeded",
                "{} includes {} seats but this workspace has {} members. Remove members "
                "before scheduling the downgrade.".format(
                    target_plan.title(), allowed_seats, seats_used),
                ["API_REFERENCE seat_limit_exceeded"],
            )
        # Downgrades are next_cycle only; the sandbox rejects effective=now with 422.
        return PlanChangeDecision(
            True, direction, "next_cycle", "downgrade_next_cycle",
            "Downgrades take effect at the end of the current billing period, so you keep "
            "what you have already paid for until then.",
            ["API_REFERENCE invalid_effective_date"],
        )

    return PlanChangeDecision(
        True, direction, "now", "{}_allowed".format(direction),
        "Upgrades and billing-cycle changes can take effect immediately with a prorated "
        "charge, or at the next cycle if you prefer.", [],
    )
