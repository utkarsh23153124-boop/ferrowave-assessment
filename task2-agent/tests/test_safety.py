"""The three rules that override everything, tested end to end through the graph.

  1. never move money policy does not allow
  2. never move it twice
  3. never tell a customer something happened that did not

Each test drives the real graph with a scripted model, so the model is free to propose
anything, including things it should never propose. What is under test is that the code
around it refuses.
"""
from __future__ import annotations

import pytest
from conftest import plan

MAYA = "maya.chen@lumenbooks.example"           # growth/monthly, inv_1001 refundable
DANIEL = "daniel@brightcart.example"            # growth/monthly, inv_1003 renewal, 24 days
PRIYA = "priya@tolland.example"                 # starter/annual, inv_1011, 11 days
AHMED = "ahmed@meridian-systems.example"        # enterprise
NADIA = "nadia@boulos-studio.example"           # inv_1060 = 9900 renewal + 2700 seats
TOMAS = "tomas.rivera@casaverde.example"        # growth, 12 seats used


# --- rule 1: never move money policy does not allow -------------------------
def test_refund_outside_the_window_moves_nothing(make_agent, admin):
    agent = make_agent(DANIEL, [plan(reply="Refunding.", kind="refund", invoice_id="inv_1003")])
    agent.send("refund my last charge")
    assert agent.last_turn["policy_result"]["allowed"] is False
    assert admin.ledger()["refunds"] == []


def test_enterprise_refund_moves_nothing(make_agent, admin):
    agent = make_agent(AHMED, [plan(reply="Sure.", kind="refund")])
    agent.send("refund my contract")
    assert agent.last_turn["policy_result"]["code"] == "enterprise_contract"
    assert admin.ledger()["refunds"] == []


def test_denied_refund_never_reaches_the_approver(make_agent):
    """A refusal is decided by code, so no human is asked to rubber-stamp it."""
    asked = []
    agent = make_agent(DANIEL, [plan(reply="ok", kind="refund", invoice_id="inv_1003")],
                       approver=lambda r: asked.append(r) or True)
    agent.send("refund please")
    assert asked == []


def test_human_refusal_stops_an_otherwise_allowed_refund(make_agent, admin):
    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001")],
                       approver=lambda r: False)
    reply = agent.send("I'd like a refund of my first month")
    assert admin.ledger()["refunds"] == []
    assert "nothing has been charged or changed" in reply
    assert agent.llm.calls == 1, "a refusal must not spend a second model call rephrasing"


def test_the_model_cannot_inflate_the_amount(make_agent, admin):
    """The model names an invoice; it never names an amount. Code sets that."""
    agent = make_agent(MAYA, [plan(reply="Refunding $10,000.", kind="refund",
                                   invoice_id="inv_1001")])
    agent.send("refund me everything you can")
    assert agent.last_turn["policy_result"]["amount_minor"] == 9900
    assert admin.ledger()["refunds"][0]["amount_minor"] == 9900


def test_seat_reversal_refunds_only_the_seat_lines_end_to_end(make_agent, admin):
    agent = make_agent(NADIA, [plan(reply="ok", kind="refund", invoice_id="inv_1060",
                                    seat_reversal_claimed=True)])
    agent.send("I added 3 seats and removed them the same day, can I get that back")
    refunds = admin.ledger()["refunds"]
    assert len(refunds) == 1
    assert refunds[0]["amount_minor"] == 2700, "the 9900 plan fee must not be refunded"


def test_seat_reversal_flags_that_a_human_must_check_the_claim(make_agent):
    seen = []
    agent = make_agent(NADIA, [plan(reply="ok", kind="refund", invoice_id="inv_1060",
                                    seat_reversal_claimed=True)],
                       approver=lambda r: seen.append(r) or False)
    agent.send("added and removed seats same day")
    assert seen[0]["needs_human_evidence"] is True


def test_ambiguous_invoice_is_asked_about_not_guessed(make_agent, admin):
    """Tomas has four invoices; a bare 'refund me' must not pick one."""
    agent = make_agent(TOMAS, [plan(reply="ok", kind="refund")])
    agent.send("refund me")
    assert agent.last_turn["policy_result"]["code"] == "invoice_not_identified"
    assert admin.ledger()["refunds"] == []


# --- rule 2: never move money twice -----------------------------------------
def test_a_503_during_an_approved_refund_yields_exactly_one_refund(make_agent, admin):
    admin.arm("refund_commit_then_503", 1)
    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001")])
    agent.send("refund my first month please")
    assert len(admin.ledger()["refunds"]) == 1
    assert agent.last_turn["execution"]["ok"] is True


def test_asking_twice_does_not_refund_twice(make_agent, admin):
    """The second request finds the invoice already refunded and policy refuses it."""
    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001"),
                              plan(reply="ok", kind="refund", invoice_id="inv_1001")])
    agent.send("refund my first month")
    agent.state["invoices"] = []          # force a fresh read, as a new turn would
    agent.state["subscription"] = None
    agent.send("actually, refund it again")
    assert len(admin.ledger()["refunds"]) == 1
    assert agent.last_turn["policy_result"]["allowed"] is False


# --- rule 3: never claim something that did not happen ----------------------
def test_unknown_outcome_escalates_and_claims_nothing(make_agent, admin, monkeypatch):
    from billing.sandbox_client import RefundOutcomeUnknown

    def explode(*args, **kwargs):
        raise RefundOutcomeUnknown("refund_outcome_unknown", "could not confirm")

    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001")])
    monkeypatch.setattr(agent.client, "create_refund", explode)
    reply = agent.send("refund my first month")

    assert agent.last_turn["escalated"] is True
    assert "will not tell you it succeeded or failed" in reply
    for word in ("refunded", "has been processed", "is complete"):
        assert word not in reply.lower()


def test_the_confirmation_sentence_is_written_by_code_not_the_model(make_agent, admin):
    """The model's prose may be vague; the factual sentence must not be.

    Running the same conversation twice against gpt-4o-mini produced "a full refund is
    available" once and "has been processed" the next time, for an identical completed
    refund. Only the second is true after the money moved, so the confirmation is now
    generated from the execution record. See ITERATIONS.md.
    """
    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001")])
    reply = agent.send("refund my first month")
    refund_id = admin.ledger()["refunds"][0]["id"]
    assert "$99.00 has been refunded" in reply
    assert refund_id in reply


def test_no_confirmation_sentence_when_nothing_happened(make_agent, admin):
    agent = make_agent(DANIEL, [plan(reply="ok", kind="refund", invoice_id="inv_1003")])
    reply = agent.send("refund my renewal")
    assert "Confirmed:" not in reply
    assert admin.ledger()["refunds"] == []


def test_escalation_sentence_appears_at_most_once(make_agent):
    from billing.graph import ESCALATION_LINE
    from billing.llm import ProposedAction, TurnPlan

    echoed = "I cannot help with that. " + ESCALATION_LINE
    agent = make_agent(MAYA, [TurnPlan(reply=echoed, action=ProposedAction(kind="none"),
                                       needs_human=True)])
    reply = agent.send("my dashboard is broken")
    assert reply.count(ESCALATION_LINE) == 1


def test_the_model_is_only_ever_shown_what_actually_happened(make_agent, admin):
    """The reply is written from an execution record, not from the model's own guess."""
    agent = make_agent(MAYA, [plan(reply="ok", kind="refund", invoice_id="inv_1001")])
    agent.send("refund my first month")
    facts = agent.llm.seen_policy_results[-1]
    assert facts["what_actually_happened"]["ok"] is True
    assert facts["what_actually_happened"]["amount_minor"] == 9900


# --- plan changes -----------------------------------------------------------
def test_downgrade_is_scheduled_for_next_cycle_not_now():
    """PM spec point 5 wants immediate downgrades; the billing system returns 422 for them.

    Asserted at the policy layer because, as the next test records, no fixture customer
    can actually reach a successful downgrade.
    """
    from billing.policy import evaluate_plan_change

    decision = evaluate_plan_change(
        {"plan": "scale", "billing_cycle": "monthly", "seats_used": 4}, "growth")
    assert decision.allowed is True and decision.effective == "next_cycle"


def test_no_fixture_customer_can_downgrade_without_removing_members(client):
    """Every seeded workspace exceeds the seat allowance of every lower plan.

    Found while writing these tests: the first version asserted a successful downgrade for
    Maya and failed, because Starter includes 3 seats and she uses 4. Checking all 14
    showed the same for every customer. Recorded in ITERATIONS.md and DECISIONS.md, since
    it means "downgrade me" in the live session will always hit the seat rule first.
    """
    from billing.policy import SEATS_INCLUDED, evaluate_plan_change

    emails = [MAYA, DANIEL, PRIYA, NADIA, TOMAS, "grace@oakline-retail.example",
              "ben@carterco.example", "ingrid@fjordhealth.example"]
    for email in emails:
        customer = client.find_customers(email)[0]
        sub = client.get_subscription(customer["id"])
        for target in ("starter", "growth"):
            if SEATS_INCLUDED[target] >= SEATS_INCLUDED[sub["plan"]]:
                continue
            decision = evaluate_plan_change(sub, target)
            assert decision.code in ("seat_limit_exceeded", "already_on_plan"), \
                "{} -> {} unexpectedly allowed".format(email, target)


def test_downgrade_over_the_seat_limit_is_refused(make_agent, admin):
    """Tomas has 12 members; starter includes 3."""
    agent = make_agent(TOMAS, [plan(reply="ok", kind="plan_change", plan="starter")])
    agent.send("put me on starter")
    assert agent.last_turn["policy_result"]["code"] == "seat_limit_exceeded"
    assert admin.ledger()["plan_changes"] == []
    assert "Remove members" in agent.last_turn["policy_result"]["explanation"]


def test_upgrade_is_applied_immediately(make_agent, admin):
    agent = make_agent(MAYA, [plan(reply="ok", kind="plan_change", plan="scale")])
    agent.send("upgrade me to scale")
    changes = admin.ledger()["plan_changes"]
    assert len(changes) == 1
    assert changes[0]["direction"] == "upgrade" and changes[0]["effective"] == "now"


def test_cycle_change_is_allowed(make_agent, admin):
    agent = make_agent(MAYA, [plan(reply="ok", kind="plan_change", plan="growth",
                                   billing_cycle="annual")])
    agent.send("switch me to annual billing")
    changes = admin.ledger()["plan_changes"]
    assert len(changes) == 1 and changes[0]["direction"] == "cycle_change"


def test_plan_change_also_requires_approval(make_agent, admin):
    """Plan changes move money too, so they go through the same gate as refunds."""
    agent = make_agent(MAYA, [plan(reply="ok", kind="plan_change", plan="scale")],
                       approver=lambda r: False)
    agent.send("upgrade me to scale")
    assert admin.ledger()["plan_changes"] == []


def test_enterprise_plan_change_is_refused_before_the_api_is_called(make_agent, admin):
    agent = make_agent(AHMED, [plan(reply="ok", kind="plan_change", plan="scale")])
    agent.send("move me to scale")
    assert agent.last_turn["policy_result"]["code"] == "enterprise_plan_restriction"
    assert admin.ledger()["plan_changes"] == []
    paths = [c["path"] for c in admin.ledger()["request_log"] if c["method"] == "POST"]
    assert not any("change" in p for p in paths)


def test_annual_refund_uses_the_prorated_amount(make_agent, admin):
    agent = make_agent(PRIYA, [plan(reply="ok", kind="refund", invoice_id="inv_1011")])
    agent.send("cancel and refund my annual plan")
    refunds = admin.ledger()["refunds"]
    assert len(refunds) == 1
    assert refunds[0]["amount_minor"] < 29000, "must be prorated, not the full charge"
    assert agent.last_turn["policy_result"]["proration"]["days_in_period"] == 365


# --- non-billing questions --------------------------------------------------
def test_out_of_scope_requests_escalate_without_touching_billing(make_agent, admin):
    from billing.llm import ProposedAction, TurnPlan

    agent = make_agent(MAYA, [TurnPlan(reply="That is a product question.",
                                       action=ProposedAction(kind="none"),
                                       needs_human=True)])
    reply = agent.send("why is my NPS score dropping")
    assert "human colleague" in reply
    assert admin.ledger()["refunds"] == []
