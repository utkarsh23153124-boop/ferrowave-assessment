"""Identity: one email address can be several customers.

`sam.okafor@northfield.example` owns cust_0003 ('Northfield Pilot', starter/monthly, US)
and cust_0004 ('Northfield Main', scale/annual, EU). Acting on the first match would mean
refunding or downgrading the wrong workspace, so the agent must resolve it first.
"""
from __future__ import annotations

from conftest import plan

SAM = "sam.okafor@northfield.example"
MAYA = "maya.chen@lumenbooks.example"


def test_the_fixture_really_is_ambiguous(client):
    assert len(client.find_customers(SAM)) == 2


def test_ambiguous_email_asks_which_workspace_and_touches_nothing(make_agent, admin):
    agent = make_agent(SAM, [plan(reply="should never be used", kind="refund",
                                  invoice_id="inv_1005")])
    reply = agent.send("I want a refund")

    assert "workspace" in reply.lower()
    assert "Northfield Pilot" in reply and "Northfield Main" in reply
    assert agent.state["awaiting"] == "disambiguation"
    assert admin.ledger()["refunds"] == [], "nothing may move before identity is settled"
    assert agent.llm.calls == 0, "and the model is not even consulted yet"


def test_naming_the_workspace_resolves_it(make_agent):
    agent = make_agent(SAM, [plan(reply="Here are your details.")])
    agent.send("refund please")
    agent.send("the Main one")
    assert agent.state["customer"]["id"] == "cust_0004"
    assert agent.state["awaiting"] is None


def test_an_unclear_answer_asks_again_rather_than_guessing(make_agent, admin):
    agent = make_agent(SAM, [plan(reply="x")])
    agent.send("refund please")
    reply = agent.send("yes")            # matches neither workspace
    assert "could not tell which workspace" in reply.lower()
    assert agent.state["awaiting"] == "disambiguation"
    assert admin.ledger()["refunds"] == []


def test_an_answer_matching_both_is_not_a_guess(make_agent):
    """'Northfield' is in both names, so it must not silently select one."""
    agent = make_agent(SAM, [plan(reply="x")])
    agent.send("refund please")
    agent.send("northfield")
    assert agent.state["customer"] is None


def test_unambiguous_email_needs_no_question(make_agent):
    agent = make_agent(MAYA, [plan(reply="Hello.")])
    agent.send("hi")
    assert agent.state["customer"]["id"] == "cust_0001"
    assert agent.state["awaiting"] is None


def test_unknown_email_escalates_without_inventing_an_account(make_agent):
    agent = make_agent("nobody@example.invalid", [plan(reply="x")])
    reply = agent.send("where is my invoice")
    assert "could not find" in reply.lower()
    assert agent.state["customer"] is None


def test_the_wrong_workspace_data_never_enters_the_context(make_agent):
    """After picking Pilot, the model must not see Main's scale/annual subscription."""
    agent = make_agent(SAM, [plan(reply="x"), plan(reply="y")])
    agent.send("hello")
    agent.send("the Pilot workspace")
    agent.send("what plan am I on")
    context = agent.llm.seen_context[-1]
    assert "starter" in context
    assert "scale" not in context
