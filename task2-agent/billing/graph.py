"""The conversation as an explicit state machine.

The graph exists so that the path money takes is a fixed sequence of nodes rather than
whatever the model decides to do next. A refund can only reach the billing system by
travelling identify -> load_context -> converse -> policy_gate -> approve -> execute,
and every one of those nodes except `converse` is plain Python.

    START
      |
      v
  [identify]  email -> customer records (email is not unique)
      |  0 found -> [escalate]
      |  >1 found -> [disambiguate] --(customer picks)--> back to identify
      |  1 found
      v
  [load_context]  subscription + invoices, notes already stripped by the client
      |
      v
  [converse]  <-- the only model call. Produces reply + proposed action.
      |
      |  action == none ---------------------------> [respond]
      |  action == refund | plan_change
      v
  [policy_gate]  policy.py decides. Model output cannot widen this.
      |
      |  denied ---------------------------------> [respond]  (explains, cites clause)
      |  needs_human_evidence ------------------->  [approve]
      |  allowed
      v
  [approve]  human types y/n in the same terminal
      |
      |  refused --------------------------------> [respond]
      |  granted
      v
  [execute]  idempotent POST; 503 is reconciled by replaying the key
      |
      |  outcome unknown ------------------------> [escalate]  (never claims success)
      |  done
      v
  [respond]  states only what the ledger confirms
      |
      v
     END
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .money import fmt
from .policy import cap_refund_amount, evaluate_plan_change, evaluate_refund
from .sandbox_client import (BillingError, RefundOutcomeUnknown, SandboxClient,
                             new_idempotency_key)

ESCALATION_LINE = ("I am handing this to a human colleague on the billing team, who will "
                   "follow up by email at the address on your account.")


class ConvState(TypedDict, total=False):
    email: str
    user_message: str
    history: list
    candidates: list
    customer: Optional[dict]
    subscription: Optional[dict]
    invoices: list
    awaiting: Optional[str]        # None | "disambiguation" | "approval"
    action: Optional[dict]
    policy_result: Optional[dict]
    execution: Optional[dict]
    reply: str
    escalated: bool


def _invoice_line(inv: dict) -> str:
    parts = ", ".join(
        "{} {}".format(li.get("description"), fmt(li.get("amount_minor"), inv["currency"]))
        for li in (inv.get("line_items") or []))
    return "  {} ({}) {} issued {} status {}{}".format(
        inv["id"], inv.get("number"), fmt(inv["amount_minor"], inv["currency"]),
        inv["issued_at"][:10], inv["status"],
        "; lines: " + parts if parts else "")


def _confirmation_line(execution: Optional[dict]) -> str:
    """The factual sentence about a completed action, written by code.

    Returns "" when nothing completed, so that no confirmation is ever produced for an
    action that did not happen.
    """
    if not execution or not execution.get("ok"):
        return ""
    if execution.get("kind") == "refund":
        return ("Confirmed: {} has been refunded to your original payment method "
                "(reference {}). It usually takes 5 to 10 business days to appear."
                .format(execution["amount_display"], execution["id"]))
    if execution.get("effective") == "now":
        return "Confirmed: your plan is now {} (reference {}).".format(
            execution["to_plan"], execution["id"])
    return "Confirmed: your plan changes to {} on {} (reference {}).".format(
        execution["to_plan"], (execution.get("effective_at") or "")[:10], execution["id"])


def build_context_block(customer: dict, subscription: dict, invoices: list, now) -> str:
    """A compact account summary. Built by code, so no raw record reaches the model.

    `customer.notes` never arrives here: SandboxClient deletes it at the boundary.
    """
    sub = subscription or {}
    lines = [
        "Today (billing system clock): {}".format(now.strftime("%Y-%m-%d")),
        "Customer: {} <{}>, workspace '{}', language {}".format(
            customer.get("name"), customer.get("email"),
            customer.get("workspace_name"), customer.get("locale")),
        "Subscription: {} plan, billed {}, status {}, {} of {} seats used, price {}".format(
            sub.get("plan"), sub.get("billing_cycle"), sub.get("status"),
            sub.get("seats_used"), sub.get("seats_included"),
            fmt(sub.get("price_minor"), sub.get("currency") or "USD")),
    ]
    if sub.get("pending_change"):
        lines.append("Pending change already scheduled: {}".format(sub["pending_change"]))
    lines.append("Recent invoices (newest first):")
    lines.extend(_invoice_line(i) for i in invoices[:6])
    if len(invoices) > 6:
        lines.append("  ... and {} older invoices".format(len(invoices) - 6))
    return "\n".join(lines)


class BillingAgent:
    """Holds the compiled graph plus the conversation state between turns."""

    def __init__(
        self,
        email: str,
        client: SandboxClient,
        llm,
        approver: Callable[[dict], bool],
        trace: Optional[Callable[[dict], None]] = None,
    ):
        self.client = client
        self.llm = llm
        self.approver = approver
        self._trace = trace
        self.state: ConvState = {
            "email": email, "history": [], "candidates": [], "invoices": [],
            "awaiting": None, "escalated": False,
        }
        self.graph = self._build()

    def _emit(self, event: dict) -> None:
        if self._trace:
            self._trace(event)

    # --- nodes ------------------------------------------------------------
    def identify(self, state: ConvState) -> dict:
        """Resolve the email to exactly one customer record.

        API_REFERENCE.md: "Email addresses are not unique. One person can own several
        workspaces, each of which is a separate customer record." Picking the first match
        would silently act on the wrong workspace, so more than one match must be resolved
        with the customer before anything else happens.
        """
        if state.get("customer"):
            return {}

        # Answering a disambiguation question we asked on a previous turn.
        if state.get("awaiting") == "disambiguation":
            picked = self._match_workspace(state.get("candidates") or [],
                                           state.get("user_message") or "")
            if picked:
                self._emit({"tool": "disambiguate", "args": {"reply": state.get("user_message")},
                            "result": "selected {} ({})".format(picked["id"],
                                                                picked.get("workspace_name"))})
                return {"customer": picked, "awaiting": None}
            names = " or ".join("'{}'".format(c.get("workspace_name"))
                                for c in state.get("candidates") or [])
            return {"reply": "Sorry, I could not tell which workspace you mean. Is it {}?".format(names),
                    "awaiting": "disambiguation"}

        try:
            found = self.client.find_customers(state["email"])
        except BillingError as exc:
            return {"reply": "I cannot reach the billing system right now. " + ESCALATION_LINE,
                    "escalated": True, "policy_result": {"error": exc.code}}

        if not found:
            return {"reply": "I could not find a Ferrowave account for {}. " .format(state["email"])
                             + "If you use a different address for billing, tell me which one.",
                    "escalated": True}
        if len(found) == 1:
            return {"customer": found[0]}

        listing = " and ".join(
            "'{}' ({} plan)".format(
                c.get("workspace_name"),
                (self._safe_sub(c) or {}).get("plan", "unknown")) for c in found)
        return {"candidates": found, "awaiting": "disambiguation",
                "reply": ("That email is on {} Ferrowave workspaces: {}. Which one are you "
                          "asking about?".format(len(found), listing))}

    def _safe_sub(self, customer: dict):
        try:
            return self.client.get_subscription(customer["id"])
        except BillingError:
            return None

    @staticmethod
    def _match_workspace(candidates: list, text: str):
        """Match a free-text reply to one workspace. Ambiguous input matches nothing."""
        low = (text or "").lower()
        hits = []
        for c in candidates:
            name = (c.get("workspace_name") or "").lower()
            tokens = [t for t in name.split() if len(t) > 3]
            if name and name in low:
                hits.append(c)
            elif c["id"].lower() in low:
                hits.append(c)
            elif any(t in low for t in tokens):
                hits.append(c)
        return hits[0] if len(hits) == 1 else None

    def load_context(self, state: ConvState) -> dict:
        if state.get("subscription") and state.get("invoices"):
            return {}
        customer = state["customer"]
        try:
            sub = self.client.get_subscription(customer["id"])
            invoices = self.client.list_invoices(customer["id"])
        except BillingError as exc:
            return {"reply": "I cannot read your billing details right now. " + ESCALATION_LINE,
                    "escalated": True, "policy_result": {"error": exc.code}}
        return {"subscription": sub, "invoices": invoices}

    def converse(self, state: ConvState) -> dict:
        """The single model call for this turn."""
        context = build_context_block(state["customer"], state["subscription"],
                                      state["invoices"], self.client.sandbox_now())
        history = list(state.get("history") or []) + [("customer", state["user_message"])]
        plan = self.llm.plan_turn(history, context)
        action = plan.action.model_dump() if plan.action else {"kind": "none"}
        if plan.needs_human:
            # The model sometimes echoes the escalation sentence back from history; it
            # must appear exactly once.
            reply = plan.reply if ESCALATION_LINE in plan.reply else (
                plan.reply.rstrip() + " " + ESCALATION_LINE)
            return {"reply": reply, "escalated": True, "action": {"kind": "none"}}
        return {"reply": plan.reply, "action": action}

    def policy_gate(self, state: ConvState) -> dict:
        """Code decides. The model's proposal is an input here, never an authorisation."""
        action = state.get("action") or {}
        sub = state["subscription"]
        now = self.client.sandbox_now()

        if action.get("kind") == "refund":
            invoice = self._resolve_invoice(state, action.get("invoice_id"))
            if invoice is None:
                return {"policy_result": {"allowed": False, "code": "invoice_not_identified",
                                          "explanation": "I could not tell which charge you "
                                          "mean. Which invoice number is it?"}}
            decision = evaluate_refund(invoice, sub, now,
                                       seat_reversal_claimed=bool(action.get("seat_reversal_claimed")))
            result = decision.to_dict()
            result["invoice_id"] = invoice["id"]
            result["currency"] = invoice["currency"]
            if decision.allowed:
                # For an annual refund the policy is prorated; the sandbox computes the
                # amount, code applies the cap. The model never touches these numbers.
                amount = decision.max_amount_minor
                if (sub.get("billing_cycle") or "").lower() == "annual":
                    try:
                        preview = self.client.refund_preview(invoice["id"])
                        amount = min(amount, int(preview["prorated_unused_minor"]))
                        result["proration"] = {
                            "days_used": preview.get("days_used"),
                            "days_in_period": preview.get("days_in_period"),
                        }
                    except BillingError as exc:
                        return {"policy_result": {"allowed": False, "code": exc.code,
                                                  "explanation": "I could not calculate the "
                                                  "prorated amount. " + ESCALATION_LINE},
                                "escalated": True}
                result["amount_minor"] = cap_refund_amount(decision, amount)
                result["amount_display"] = fmt(result["amount_minor"], invoice["currency"])
            self._emit({"tool": "policy.evaluate_refund",
                        "args": {"invoice_id": invoice["id"], "plan": sub.get("plan"),
                                 "cycle": sub.get("billing_cycle")},
                        "result": {k: result[k] for k in ("allowed", "code") if k in result}})
            return {"policy_result": result}

        if action.get("kind") == "plan_change":
            decision = evaluate_plan_change(sub, action.get("plan") or "",
                                            action.get("billing_cycle"))
            result = decision.to_dict()
            self._emit({"tool": "policy.evaluate_plan_change",
                        "args": {"target": action.get("plan"),
                                 "cycle": action.get("billing_cycle")},
                        "result": {"allowed": result["allowed"], "code": result["code"]}})
            return {"policy_result": result}

        return {"policy_result": None}

    def _resolve_invoice(self, state: ConvState, invoice_id: Optional[str]):
        invoices = state.get("invoices") or []
        if invoice_id:
            for inv in invoices:
                if inv["id"] == invoice_id or inv.get("number") == invoice_id:
                    return inv
            return None
        # No invoice named: only unambiguous when there is exactly one refundable charge.
        candidates = [i for i in invoices if i.get("status") in ("paid", "partially_refunded")]
        return candidates[0] if len(candidates) == 1 else None

    def approve(self, state: ConvState) -> dict:
        """Human approval. PM spec point 3: a human approves before money moves."""
        result = state["policy_result"]
        action = state.get("action") or {}
        request = {
            "kind": action.get("kind"),
            "customer": state["customer"].get("name"),
            "workspace": state["customer"].get("workspace_name"),
            "policy_code": result.get("code"),
            "explanation": result.get("explanation"),
            "needs_human_evidence": result.get("needs_human_evidence", False),
        }
        if action.get("kind") == "refund":
            request.update({"invoice_id": result.get("invoice_id"),
                            "amount": result.get("amount_display"),
                            "amount_minor": result.get("amount_minor")})
        else:
            request.update({"to_plan": action.get("plan"),
                            "direction": result.get("direction"),
                            "effective": result.get("effective")})

        granted = bool(self.approver(request))
        self._emit({"tool": "human_approval", "args": request,
                    "result": "granted" if granted else "refused"})
        if granted:
            return {}
        return {"reply": "I asked a colleague to review this and they have not approved it, "
                         "so nothing has been charged or changed. They will follow up with you.",
                "policy_result": dict(result, approved=False)}

    def execute(self, state: ConvState) -> dict:
        """The only place that moves money. Everything here is idempotent."""
        action = state.get("action") or {}
        result = state["policy_result"]
        try:
            if action.get("kind") == "refund":
                refund, replayed = self.client.create_refund(
                    invoice_id=result["invoice_id"],
                    amount_minor=result["amount_minor"],
                    reason="{} ({})".format(
                        ", ".join(result.get("cites") or []) or "policy", result["code"]),
                    idempotency_key=new_idempotency_key("refund"),
                )
                return {"execution": {"ok": True, "kind": "refund", "id": refund["id"],
                                      "amount_minor": refund["amount_minor"],
                                      "amount_display": fmt(refund["amount_minor"],
                                                            refund.get("currency", "USD")),
                                      "replayed": replayed}}
            change, replayed = self.client.change_plan(
                subscription_id=state["subscription"]["id"],
                plan=action.get("plan"),
                effective=result.get("effective"),
                billing_cycle=action.get("billing_cycle"),
                idempotency_key=new_idempotency_key("change"),
            )
            return {"execution": {"ok": True, "kind": "plan_change", "id": change["id"],
                                  "to_plan": change["to_plan"], "effective": change["effective"],
                                  "effective_at": change["effective_at"], "replayed": replayed}}
        except RefundOutcomeUnknown as exc:
            # Requirement 1: never tell the customer something happened that did not.
            return {"execution": {"ok": False, "unknown": True, "detail": exc.message},
                    "escalated": True,
                    "reply": ("Your request reached our billing system but it did not confirm "
                              "the result, so I will not tell you it succeeded or failed. "
                              + ESCALATION_LINE + " They will confirm within one business day.")}
        except BillingError as exc:
            return {"execution": {"ok": False, "error": exc.code, "detail": exc.message}}

    def respond(self, state: ConvState) -> dict:
        """Phrase the outcome. The model may only restate what code established."""
        execution = state.get("execution")
        policy_result = state.get("policy_result")
        if state.get("reply") and not execution and not policy_result:
            return {}
        if state.get("escalated"):
            return {}

        facts: dict = {}
        if policy_result:
            facts["policy"] = policy_result
        if execution:
            facts["what_actually_happened"] = execution
        if not facts:
            return {}

        context = build_context_block(state["customer"], state["subscription"],
                                      state["invoices"], self.client.sandbox_now())
        history = list(state.get("history") or []) + [("customer", state["user_message"])]
        plan = self.llm.plan_turn(history, context, policy_result=facts)
        reply = plan.reply

        # The sentence that states what happened to a customer's money is written by
        # code, not by the model. Asked the same question twice, the model phrased a
        # completed refund as "a full refund is available" one run and "has been
        # processed" the next; only one of those is true after the money has moved.
        confirmation = _confirmation_line(execution)
        if confirmation and confirmation not in reply:
            reply = reply.rstrip() + " " + confirmation
        return {"reply": reply}

    def escalate(self, state: ConvState) -> dict:
        if state.get("reply"):
            return {"escalated": True}
        return {"reply": ESCALATION_LINE, "escalated": True}

    # --- edges ------------------------------------------------------------
    @staticmethod
    def _after_identify(state: ConvState) -> str:
        if state.get("escalated"):
            return "escalate"
        if state.get("customer"):
            return "load_context"
        return "end"          # a disambiguation question is already in `reply`

    @staticmethod
    def _after_load(state: ConvState) -> str:
        return "escalate" if state.get("escalated") else "converse"

    @staticmethod
    def _after_converse(state: ConvState) -> str:
        if state.get("escalated"):
            return "end"
        kind = (state.get("action") or {}).get("kind")
        return "policy_gate" if kind in ("refund", "plan_change") else "end"

    @staticmethod
    def _after_gate(state: ConvState) -> str:
        result = state.get("policy_result")
        if state.get("escalated"):
            return "escalate"
        if not result or not result.get("allowed"):
            return "respond"
        return "approve"

    @staticmethod
    def _after_approve(state: ConvState) -> str:
        result = state.get("policy_result") or {}
        # A refusal already has its wording from `approve`. Going through `respond` would
        # spend a model call to rephrase a sentence that must not drift, so it ends here.
        return "end" if result.get("approved") is False else "execute"

    @staticmethod
    def _after_execute(state: ConvState) -> str:
        execution = state.get("execution") or {}
        return "escalate" if execution.get("unknown") else "respond"

    def _build(self):
        g = StateGraph(ConvState)
        g.add_node("identify", self.identify)
        g.add_node("load_context", self.load_context)
        g.add_node("converse", self.converse)
        g.add_node("policy_gate", self.policy_gate)
        g.add_node("approve", self.approve)
        g.add_node("execute", self.execute)
        g.add_node("respond", self.respond)
        g.add_node("escalate", self.escalate)

        g.add_edge(START, "identify")
        g.add_conditional_edges("identify", self._after_identify,
                                {"load_context": "load_context", "escalate": "escalate", "end": END})
        g.add_conditional_edges("load_context", self._after_load,
                                {"converse": "converse", "escalate": "escalate"})
        g.add_conditional_edges("converse", self._after_converse,
                                {"policy_gate": "policy_gate", "end": END})
        g.add_conditional_edges("policy_gate", self._after_gate,
                                {"approve": "approve", "respond": "respond", "escalate": "escalate"})
        g.add_conditional_edges("approve", self._after_approve,
                                {"execute": "execute", "end": END})
        g.add_conditional_edges("execute", self._after_execute,
                                {"respond": "respond", "escalate": "escalate"})
        g.add_edge("respond", END)
        g.add_edge("escalate", END)
        return g.compile()

    # --- driving ----------------------------------------------------------
    def send(self, user_message: str) -> str:
        """Run one customer turn through the graph and return the reply."""
        turn_state = dict(self.state)
        turn_state.update({"user_message": user_message, "reply": "",
                           "action": None, "policy_result": None, "execution": None,
                           "escalated": False})
        out = self.graph.invoke(turn_state)

        reply = out.get("reply") or "Sorry, I do not have an answer for that."
        history = list(self.state.get("history") or [])
        history.extend([("customer", user_message), ("agent", reply)])

        subscription = out.get("subscription") or self.state.get("subscription")
        invoices = out.get("invoices") or self.state.get("invoices")

        # A write invalidates the cached account. Without this, a customer who asks twice
        # in one conversation is judged on the state from before the first refund: policy
        # sees refunded_minor=0, rules the refund allowed a second time, and puts a
        # duplicate request in front of the approver. The sandbox rejects the write with
        # invalid_state, so no money moves, but relying on that is relying on the other
        # side's guard. Re-read instead.
        if (out.get("execution") or {}).get("ok"):
            subscription, invoices = None, []

        self.state.update({
            "history": history,
            "customer": out.get("customer") or self.state.get("customer"),
            "subscription": subscription,
            "invoices": invoices,
            "candidates": out.get("candidates") or self.state.get("candidates"),
            "awaiting": out.get("awaiting"),
        })
        self.last_turn = {"policy_result": out.get("policy_result"),
                          "execution": out.get("execution"),
                          "action": out.get("action"),
                          "escalated": out.get("escalated", False)}
        return reply
