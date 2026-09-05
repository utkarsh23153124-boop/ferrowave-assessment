"""Transcript recording.

PM spec point 10 asks for every tool call to be logged so finance can audit what the agent
did. The transcript is written on exit and contains every turn, every sandbox call with
arguments and results, every policy decision, every approval, and token usage.

Nothing written here has passed through `customer.notes`; the client deletes that field
before any caller sees it, so it cannot reach this file either.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


class Transcript:
    def __init__(self, email: str, sandbox_url: str, model: str, directory: str = "transcripts"):
        self.directory = directory
        self.started_at = datetime.now(timezone.utc)
        self.meta = {"email": email, "sandbox": sandbox_url, "model": model,
                     "started_at": self.started_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.turns: list = []
        self.tool_calls: list = []
        self._pending: list = []

    def record_tool_call(self, event: dict) -> None:
        stamped = dict(event)
        stamped["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.tool_calls.append(stamped)
        self._pending.append(stamped)

    def record_turn(self, customer: str, agent: str, detail: dict) -> None:
        self.turns.append({
            "n": len(self.turns) + 1,
            "customer": customer,
            "agent": agent,
            "policy_result": detail.get("policy_result"),
            "execution": detail.get("execution"),
            "action": detail.get("action"),
            "escalated": detail.get("escalated", False),
            "tool_calls": self._pending,
        })
        self._pending = []

    def write(self, usage: dict) -> str:
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(
            self.directory, self.started_at.strftime("%Y%m%dT%H%M%SZ") + ".json")
        payload = {
            **self.meta,
            "ended_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "turn_count": len(self.turns),
            "usage": usage,
            "turns": self.turns,
            "all_tool_calls": self.tool_calls,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return path
