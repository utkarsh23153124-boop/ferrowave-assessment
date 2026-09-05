"""Test harness.

The tests start their own copy of the sandbox on a free port, so `python -m pytest` works
from a clean clone with nothing else running. No test needs an API key: the model is
replaced by a scripted stand-in, because what is under test is the policy and failure
handling, which are deliberately model-free.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(os.path.dirname(ROOT), "sandbox", "server.py")
sys.path.insert(0, ROOT)

from billing.graph import BillingAgent            # noqa: E402
from billing.llm import ProposedAction, TurnPlan  # noqa: E402
from billing.sandbox_client import SandboxClient  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def sandbox_url():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, SANDBOX, "--port", str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:{}".format(port)
    for _ in range(100):
        try:
            if requests.get(url + "/health", timeout=1).ok:
                break
        except requests.RequestException:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("sandbox did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def admin(sandbox_url):
    """Evaluator-side controls. The agent itself may never call these."""

    class Admin:
        def reset(self):
            requests.post(sandbox_url + "/_admin/reset", timeout=5)

        def arm(self, mode, count=1):
            requests.post(sandbox_url + "/_admin/chaos",
                          json={"mode": mode, "count": count}, timeout=5)

        def clear(self):
            requests.post(sandbox_url + "/_admin/chaos", json={"mode": "clear"}, timeout=5)

        def ledger(self):
            return requests.get(sandbox_url + "/_admin/ledger", timeout=5).json()

    a = Admin()
    a.reset()
    a.clear()
    yield a
    a.reset()
    a.clear()


@pytest.fixture
def client(sandbox_url):
    return SandboxClient(sandbox_url, sleep=lambda s: time.sleep(min(s, 0.2)))


class FakeLLM:
    """A scripted stand-in for the model.

    Each entry in `script` is the TurnPlan the model would have produced. Using a fake
    keeps the tests deterministic and free, and proves the safety properties hold no
    matter what the model proposes, including proposals it should never make.
    """

    def __init__(self, script):
        self.script = list(script)
        self.model_name = "fake"
        self.tokens_in = self.tokens_out = self.calls = 0
        self.seen_context = []
        self.seen_policy_results = []

    def plan_turn(self, history, context_block, policy_result=None):
        self.calls += 1
        self.seen_context.append(context_block)
        if policy_result is not None:
            self.seen_policy_results.append(policy_result)
            # A real model phrases the outcome; the fake echoes it verbatim so tests can
            # assert on exactly what the agent was told it may say.
            return TurnPlan(reply="OUTCOME: " + str(policy_result),
                            action=ProposedAction(kind="none"))
        return self.script.pop(0) if self.script else TurnPlan(
            reply="ok", action=ProposedAction(kind="none"))

    def usage(self):
        return {"model": "fake", "llm_calls": self.calls, "tokens_in": 0,
                "tokens_out": 0, "estimated_cost_usd": 0.0}


def plan(reply="ok", kind="none", **kw):
    return TurnPlan(reply=reply, action=ProposedAction(kind=kind, **kw))


@pytest.fixture
def make_agent(client):
    def factory(email, script, approver=lambda req: True, trace=None):
        return BillingAgent(email, client, FakeLLM(script), approver, trace=trace)
    return factory
