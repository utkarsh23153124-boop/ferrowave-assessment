# ITERATIONS.md

Task: Task 2, Billing Helper agent. Dated log of what I built, what broke, and what the
evidence was.

## 2026-09-05, before writing any code: read the sandbox source

Read `API_REFERENCE.md` in full and then `server.py`, because the reference says the
sandbox reproduces the real system's failure modes and the brief says most of what matters
is in the given material. Three things came out of the source that the reference does not
spell out, and all three changed the design:

1. In `create_refund`, the refund is appended to state **and the idempotency key stored**
   *before* the `refund_commit_then_503` chaos check. So a replay of the same key returns
   the committed refund without re-entering the chaos path. This is what makes "retry with
   the same key" the correct recovery rather than a gamble.
2. `change_preview` validates the plan name *before* the Enterprise check, but `change_plan`
   checks Enterprise *first*. The same request gets 400 from one and 403 from the other.
   Decided to refuse Enterprise in my own code before either is called, so the inconsistency
   never reaches a customer.
3. Every non-admin request sleeps 0.10-0.35s, and `POST /refunds` a further 0.6-0.9s. That
   is what makes PM spec point 6 (3 second replies) arithmetically impossible, not just
   tight. Recorded in DECISIONS.md Spec issues 6.

Then read all 14 fixture customers. Found the prompt injection in `cust_0010.notes` and the
duplicate email on `sam.okafor@northfield.example`. The injection is what settled the design
of PM spec point 7: notes are deleted at the client boundary rather than passed with a
"do not disclose" instruction.

## 2026-09-05: policy engine first, before any agent code

Wrote `policy.py` and its 27 tests before anything that could make a network call, so that
the refund rules could be argued about on their own. Verified the outputs against the real
fixtures immediately: Maya's 9-day monthly first charge allowed at $99.00, Daniel's 24-day
renewal refused, Priya's 11-day annual allowed prorated, Ahmed's Enterprise refused, and
Nadia's $126.00 seat invoice capped at the $27.00 seat lines.

## 2026-09-05: a test premise that was wrong, and the code was right

Wrote `test_unresolvable_503_raises_rather_than_claiming_success` expecting that arming
`refund_commit_then_503` with a high count would defeat reconciliation and force the unknown
outcome branch. **It failed: DID NOT RAISE.**

The reason is finding (1) above — a stored idempotency key short-circuits ahead of the chaos
hook, so the first replay always resolves. My mental model was wrong, not the code. Split
the test in two: one asserting that many armed 503s still resolve on the first replay
(the real, better guarantee), and one that exercises the unknown-outcome branch by stubbing
a transport failure during reconciliation, which is the shape this failure actually takes in
production. Both pass.

## 2026-09-05: the approval refusal was being rewritten by the model

`test_human_refusal_stops_an_otherwise_allowed_refund` failed. No money had moved, so the
safety property held, but the reply was not the code-written refusal — the graph routed
refusals through `respond`, which called the model to rephrase them.

Two problems: the sentence telling a customer that nothing happened is exactly the sentence
that must not drift, and it was costing a model call to produce. Routed approval refusals
straight to `END`. The test now also asserts `llm.calls == 1`, so a future refactor cannot
quietly reintroduce the second call.

## 2026-09-05: a second wrong test premise, and a real finding behind it

`test_downgrade_is_scheduled_for_next_cycle_not_now` failed with zero plan changes in the
ledger. I had assumed Maya could downgrade to Starter; she uses 4 seats and Starter includes
3, so policy refused it before the API was reached.

Checked all 14 fixture customers rather than just picking a different one. **Not one of them
can downgrade to any lower plan** — every workspace exceeds the seat allowance of every plan
below it. That is a deliberate trap aimed squarely at PM spec point 5, and it means "downgrade
me" in the live session will always hit the seat rule. Replaced the test with a unit test of
the next-cycle rule plus `test_no_fixture_customer_can_downgrade_without_removing_members`,
which pins the finding, and added end-to-end tests for the upgrade and cycle-change paths
that *are* reachable.

## 2026-09-05: first real conversation, two wording defects

Ran the CLI against the live model for the first time. The refund executed and the ledger
showed exactly one $99.00 refund, but:

- the reply said "I **will** process that for you now" after the money had already moved;
- the refund reason recorded in the ledger read "Refund Policy Refund Policy 1.1", because
  `execute` prefixed a string that already contained the prefix.

Fixed the duplicated prefix, and told the model in the `POLICY RESULT` block that a present
`what_actually_happened` means the action is already complete. Re-ran: "The refund of $99.00
has been processed."

## 2026-09-05: the same fix was not enough, so I took the sentence away from the model

Re-ran the same conversation while recording the five transcripts. The identical completed
refund came back as **"a full refund is available"** — no longer false about tense, but no
longer true about state either. Prompt wording had made the failure less frequent, not
impossible, and this is the one sentence where "usually right" is not a standard.

Moved the factual clause out of the model entirely: `_confirmation_line` builds it from the
execution record, and `respond` appends it. The model still writes the surrounding prose.
Pinned by `test_the_confirmation_sentence_is_written_by_code_not_the_model`, which asserts
the amount and the refund reference appear in the reply, and by
`test_no_confirmation_sentence_when_nothing_happened`.

This is the iteration I would point at if asked which one mattered most: it moved a safety
property from "the prompt asks for it" to "the code guarantees it".

## 2026-09-05: two more defects from the same recording run

- The escalation sentence appeared **twice** in one reply. The model had copied the previous
  turn's escalation line out of the history, and `converse` appended it again. Now appended
  only when not already present; `test_escalation_sentence_appears_at_most_once`.
- The model set `needs_human` for Nadia's seat-reversal request, escalating a case that
  policy handles correctly and that the tests already covered. The schema description for
  `needs_human` was too loose. Tightened it to non-billing topics only, and told the model
  explicitly that a same-day seat add-and-remove is a normal refund with
  `seat_reversal_claimed=true`. Re-ran: $27.00 refunded, plan fee untouched.

The injection conversation improved as a side effect of the same change. Before, the model
escalated Grace's demand without policy ever ruling on it — safe, but weak. After, policy
evaluates it and the customer is told monthly renewals are not refundable, citing 1.2.

## 2026-09-05: final state

77 tests passing in about 55s, no API key required. Seven recorded conversations covering
the happy path, the injection, the duplicate email, Enterprise, the 503, and a Spanish
conversation. Mean measured cost $0.00036 per conversation.

## What I would do next, with more time

- Have the agent read `pending_change` and refuse a second plan change that would contradict
  a scheduled one. The sandbox allows it; policy has no opinion yet.
- The `_match_workspace` matcher is deliberately conservative and answers "Northfield" with a
  re-ask because it matches both workspaces. A numbered list ("reply 1 or 2") would be
  friendlier and is a small change.
- Add role checking for Refund Policy 4.2 the moment the customer record carries a role.
