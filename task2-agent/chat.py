#!/usr/bin/env python3
"""Ferrowave Billing Helper: command-line chat.

    python chat.py chat --email maya.chen@lumenbooks.example [--sandbox URL] [--trace]

The `chat` sub-command is accepted but optional, so both forms in the brief work.
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # optional convenience only
    pass

from billing.graph import BillingAgent
from billing.llm import LLM, MODEL
from billing.sandbox_client import BillingError, SandboxClient
from billing.transcript import Transcript

BANNER = """Ferrowave Billing Helper
Type your message and press enter. 'exit' or Ctrl-D ends the chat and writes the transcript.
"""


def terminal_approver(request: dict) -> bool:
    """Human approval, in the same terminal, as the interface contract requires."""
    print("\n--- APPROVAL REQUIRED " + "-" * 46)
    if request.get("kind") == "refund":
        print("  Refund {} on invoice {}".format(request.get("amount"), request.get("invoice_id")))
    else:
        print("  {} to {} plan, effective {}".format(
            (request.get("direction") or "change").title(),
            request.get("to_plan"), request.get("effective")))
    print("  Customer:  {} ({})".format(request.get("customer"), request.get("workspace")))
    print("  Policy:    {}".format(request.get("policy_code")))
    print("  Reasoning: {}".format(request.get("explanation")))
    if request.get("needs_human_evidence"):
        print("  NOTE: policy allows this only if the customer's account of events is "
              "correct.\n        The billing system cannot confirm it. Check before approving.")
    print("-" * 68)
    try:
        answer = input("Approve? [y/N] ").strip().lower()
    except EOFError:
        answer = ""
    print()
    return answer in ("y", "yes")


def make_tracer(enabled: bool, transcript: Transcript):
    def trace(event: dict) -> None:
        transcript.record_tool_call(event)
        if not enabled:
            return
        detail = event.get("result")
        line = "  [tool] {} {}".format(event.get("tool"), event.get("args") or "")
        if event.get("status") is not None:
            line += " -> {}".format(event["status"])
        if event.get("replayed"):
            line += " (idempotent replay)"
        print(line)
        if detail is not None:
            print("         {}".format(detail))
    return trace


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ferrowave Billing Helper chat")
    parser.add_argument("command", nargs="?", default="chat", choices=["chat"],
                        help="optional; only 'chat' exists")
    parser.add_argument("--email", required=True, help="customer email (treated as authenticated)")
    parser.add_argument("--sandbox", default=os.environ.get("SANDBOX_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--trace", action="store_true", help="print every tool call")
    parser.add_argument("--transcripts", default="transcripts")
    args = parser.parse_args(argv)

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.",
              file=sys.stderr)
        return 2

    transcript = Transcript(args.email, args.sandbox, MODEL, args.transcripts)
    trace = make_tracer(args.trace, transcript)
    client = SandboxClient(args.sandbox, trace=trace)

    try:
        health = client.health()
    except BillingError as exc:
        print("Cannot reach the billing sandbox at {} ({}).".format(args.sandbox, exc.message),
              file=sys.stderr)
        print("Start it with:  python ../sandbox/server.py", file=sys.stderr)
        return 2

    llm = LLM()
    agent = BillingAgent(args.email, client, llm, terminal_approver, trace=trace)

    print(BANNER)
    print("Customer: {}   sandbox clock: {}\n".format(args.email, health.get("sandbox_now")))

    while True:
        try:
            message = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message.lower() in ("exit", "quit"):
            break
        try:
            reply = agent.send(message)
        except Exception as exc:  # never crash mid-conversation on the customer
            reply = ("Something went wrong on my side, so I have not changed anything on "
                     "your account. A colleague will follow up.")
            trace({"tool": "agent_error", "args": {}, "result": str(exc)})
        print("\nagent> {}\n".format(reply))
        transcript.record_turn(message, reply, getattr(agent, "last_turn", {}))

    path = transcript.write(llm.usage())
    usage = llm.usage()
    print("Transcript: {}".format(path))
    print("This conversation: {} model call(s), {} in / {} out tokens, ${:.5f}".format(
        usage["llm_calls"], usage["tokens_in"], usage["tokens_out"],
        usage["estimated_cost_usd"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
