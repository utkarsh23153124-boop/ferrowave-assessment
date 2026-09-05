"""One test per chaos mode in `sandbox/API_REFERENCE.md`, plus the idempotency contract.

Every assertion that matters is made against `/_admin/ledger`, which the reference calls
the source of truth for what actually happened. Checking the agent's own opinion of what
it did would prove nothing.
"""
from __future__ import annotations

import time

import pytest

from billing.sandbox_client import (BillingError, RefundOutcomeUnknown, SandboxClient,
                                    new_idempotency_key)

MAYA = "maya.chen@lumenbooks.example"
MAYA_INVOICE = "inv_1001"     # monthly new_subscription, 9 days old, $99.00, refundable


# --- mode: rate_limit -------------------------------------------------------
def test_rate_limit_is_retried_after_the_interval_the_server_asks_for(client, admin):
    admin.arm("rate_limit", 3)
    customers = client.find_customers(MAYA)
    assert len(customers) == 1, "the call must succeed after backing off"
    waits = [c for c in client.calls if str(c.get("result", "")).startswith("rate_limited")]
    assert len(waits) == 3, "expected one recorded wait per 429"
    assert "waiting 2.0s" in str(waits[0]["result"]), "must use the server's Retry-After"


def test_rate_limit_gives_up_rather_than_hammering(client, admin):
    """More 429s than the retry budget must surface as an error, not an infinite loop."""
    admin.arm("rate_limit", 20)
    with pytest.raises(BillingError):
        client.find_customers(MAYA)


# --- mode: refund_commit_then_503 -------------------------------------------
def test_refund_commit_then_503_never_refunds_twice(client, admin):
    """The sandbox commits the refund, then reports a 503.

    Recovery is a replay of the same idempotency key, which short-circuits ahead of the
    chaos hook in create_refund and returns the refund that already exists.
    """
    admin.arm("refund_commit_then_503", 1)
    refund, replayed = client.create_refund(
        MAYA_INVOICE, 9900, "first month within 14 days", new_idempotency_key())

    ledger = admin.ledger()
    assert len(ledger["refunds"]) == 1, "a second refund would be a double payout"
    assert ledger["refunds"][0]["amount_minor"] == 9900
    assert refund["id"] == ledger["refunds"][0]["id"]
    assert replayed is True, "the client must know the result came from a replay"


def test_repeated_503s_are_still_a_single_refund(client, admin):
    admin.arm("refund_commit_then_503", 1)
    client.create_refund(MAYA_INVOICE, 5000, "partial", new_idempotency_key())
    assert len(admin.ledger()["refunds"]) == 1


def test_refund_without_an_idempotency_key_is_refused(client, admin):
    """Without a key a 503 is unrecoverable, so the client will not send the request."""
    with pytest.raises(BillingError) as excinfo:
        client.create_refund(MAYA_INVOICE, 9900, "reason", "")
    assert excinfo.value.code == "missing_idempotency_key"
    assert admin.ledger()["refunds"] == []


def test_many_armed_503s_still_resolve_on_the_first_replay(client, admin):
    """A replay short-circuits ahead of the chaos hook, so one retry always settles it.

    I originally expected repeated 503s to defeat reconciliation. Reading create_refund
    shows the idempotency key is stored *before* the chaos check, so the stored response
    is returned without re-entering the chaos path. Recorded in ITERATIONS.md.
    """
    admin.arm("refund_commit_then_503", 9)
    refund, replayed = client.create_refund(
        MAYA_INVOICE, 9900, "reason", new_idempotency_key())
    assert replayed is True and refund["status"] == "succeeded"
    assert len(admin.ledger()["refunds"]) == 1


def test_unresolvable_outcome_raises_rather_than_claiming_success(sandbox_url):
    """When reconciliation itself cannot complete, no refund object may be returned.

    The real-world shape of this is the connection dropping after the POST, not a chaos
    mode: the sandbox can always answer a replay, but a dead network cannot. Stubbed
    directly so the unknown-outcome branch is exercised deterministically.
    """
    c = SandboxClient(sandbox_url, sleep=lambda s: None)
    calls = {"n": 0}

    def flaky(method, path, params=None, json_body=None, idempotency_key=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return 503, {"error": {"code": "upstream_timeout", "message": "timed out"}}, {}
        raise BillingError("transport_error", "connection reset")

    c._request = flaky
    with pytest.raises(RefundOutcomeUnknown):
        c.create_refund(MAYA_INVOICE, 9900, "reason", new_idempotency_key())
    assert calls["n"] > 1, "it must at least attempt to reconcile"


# --- mode: latency_spike ----------------------------------------------------
def test_latency_spike_is_absorbed_not_timed_out(client, admin):
    admin.arm("latency_spike", 1)
    started = time.time()
    customers = client.find_customers(MAYA)
    elapsed = time.time() - started
    assert len(customers) == 1
    assert elapsed >= 5.0, "the spike should actually have been applied"
    assert elapsed < client.timeout, "and absorbed rather than raising a timeout"


# --- mode: clear ------------------------------------------------------------
def test_clear_disarms_everything(client, admin):
    admin.arm("rate_limit", 5)
    admin.arm("latency_spike", 5)
    admin.clear()
    started = time.time()
    client.find_customers(MAYA)
    assert time.time() - started < 2.0


# --- idempotency contract ---------------------------------------------------
def test_same_key_different_body_is_rejected(client, admin):
    key = new_idempotency_key()
    client.create_refund(MAYA_INVOICE, 9900, "reason", key)
    with pytest.raises(BillingError) as excinfo:
        client.create_refund(MAYA_INVOICE, 5000, "reason", key)
    assert excinfo.value.code == "idempotency_mismatch"
    assert len(admin.ledger()["refunds"]) == 1


def test_same_key_same_body_replays_the_original(client, admin):
    key = new_idempotency_key()
    first, replayed_first = client.create_refund(MAYA_INVOICE, 9900, "reason", key)
    second, replayed_second = client.create_refund(MAYA_INVOICE, 9900, "reason", key)
    assert first["id"] == second["id"]
    assert replayed_first is False and replayed_second is True
    assert len(admin.ledger()["refunds"]) == 1


# --- routes the agent must not touch ----------------------------------------
def test_admin_routes_are_unreachable_through_the_client(sandbox_url):
    c = SandboxClient(sandbox_url)
    with pytest.raises(BillingError) as excinfo:
        c._request("POST", "/_admin/reset")
    assert excinfo.value.code == "forbidden_route"
