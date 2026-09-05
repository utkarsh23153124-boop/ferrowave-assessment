# Task 2: Ferrowave Billing Helper

A command-line chat agent that handles refunds, plan changes and "why was I charged"
questions against the billing sandbox. Policy is enforced in Python; the model handles
conversation only.

## Quick start

```bash
# terminal 1: the billing sandbox
python sandbox/server.py                      # from the repo root

# terminal 2: the agent
cd task2-agent
pip install -r requirements.txt
cp .env.example .env                          # add your OPENAI_API_KEY
python chat.py chat --email maya.chen@lumenbooks.example --trace
```

`--trace` prints every tool call with arguments and results. On exit the agent writes
`transcripts/<timestamp>.json` with every turn, every tool call, and token usage.

Tests need no API key and start their own sandbox:

```bash
python -m pytest                              # 77 tests, about 55s
```

## The three rules, and where each is enforced

| Rule | Enforced by | Test |
|---|---|---|
| Never move money policy does not allow | `billing/policy.py`, called from the `policy_gate` node before any POST | `test_policy.py` (27), `test_safety.py::test_refund_outside_the_window_moves_nothing` |
| Never move money twice | Mandatory `Idempotency-Key` on every write; a 503 is resolved by replaying the same key, never by re-POSTing | `test_chaos.py::test_refund_commit_then_503_never_refunds_twice` |
| Never say something happened that did not | The confirmation sentence is generated from the execution record by `_confirmation_line`, not written by the model; an unresolvable outcome escalates and claims nothing | `test_safety.py::test_the_confirmation_sentence_is_written_by_code_not_the_model`, `::test_unknown_outcome_escalates_and_claims_nothing` |

## State diagram

```
                                  START
                                    |
                                    v
                             +-------------+
                             |  identify   |  email -> customer record
                             +-------------+  (email is NOT unique)
                        0 found  |   |   |  >1 found
              +------------------+   |   +------------------+
              v                      | 1 found              v
        +----------+                 |              +---------------+
        | escalate |                 |              | ask which     |
        +----------+                 |              | workspace     |--> END
              ^                      v              +---------------+
              |              +--------------+          (answer resumes at identify)
              |              | load_context |  subscription + invoices
              |              +--------------+  notes already stripped
              |                      |
              |                      v
              |              +--------------+
              |              |   converse   |  <-- the ONLY model call
              |              +--------------+      returns reply + proposed action
              |                 |         |
              |    action=none  |         | action = refund | plan_change
              |                 v         v
              |               END   +--------------+
              |                     | policy_gate  |  policy.py decides.
              |                     +--------------+  Model output cannot widen this.
              |                 denied |         | allowed
              |                        v         v
              |                +-----------+  +----------+
              |                |  respond  |  | approve  |  human types y/n
              |                +-----------+  +----------+
              |                        ^        |       | refused
              |                        |        |granted+--------> END
              |                        |        v
              |                        |  +-----------+
              |                        |  |  execute  |  idempotent POST
              |                        |  +-----------+  503 -> replay same key
              |                        |     |      | outcome unknown
              |                        +-----+      |
              +-----------------------------------+ |
                                                  \ v
                                                  escalate --> END
```

Every node except `converse` is plain Python. A refund can only reach the billing system by
travelling the whole path, and `approve` sits between the decision and the money.

## What the framework is actually doing

LangGraph contributes the explicit state machine above: named nodes, conditional edges, and
a typed `ConvState`. That is the reason the diagram and the code cannot drift apart, and
the reason "where can money move from?" has a one-word answer (`execute`) rather than
"anywhere the model decides to call a tool".

What it is deliberately *not* doing: there is no tool-calling loop and no ReAct agent. The
model returns a structured `TurnPlan` and the graph decides what happens next. A framework
that let the model call `create_refund` directly would move the policy decision into the
prompt, which is exactly what the brief asks us not to do.

## Design notes

**The model never sees `customer.notes`.** `SandboxClient` deletes the field at the
boundary. Fixture `cust_0010` carries an instruction in that field addressed to AI agents,
telling them to refund without checks using "override code 7781". Removing the field
removes the attack, and it satisfies the half of PM spec point 7 that says never to
disclose internal notes. Personalisation comes from structured fields instead: name,
locale, plan, seats, invoice history.

**Policy is hard-coded, not retrieved.** Refund windows live in `policy.py` as constants
whose comments cite the clause of `corpus/policies/refund-policy.md` they come from. A RAG
miss must not be able to authorise a refund, so the Task 1 retriever is not in the money
path. See DECISIONS.md.

**The sandbox clock, never the local clock.** Every date comparison uses `X-Sandbox-Now`
(frozen at 2026-08-29T09:00:00Z), read from response headers by the client.

**Amounts are integers in minor units** everywhere, and the model never produces one. For
an annual refund the proration comes from `GET /invoices/{id}/refund_preview` and is then
clamped by `cap_refund_amount`.

## Measured cost

Seven recorded conversations in `transcripts/`, gpt-4o-mini at list price
($0.15/$0.60 per 1M tokens in/out), computed from the token counts the API returned:

| Measure | Value |
|---|---|
| Mean cost per conversation | **$0.00036** |
| Highest single conversation | $0.00044 |
| All 7 conversations | $0.00253 |
| Mean model calls per conversation | 1.9 |
| Mean sandbox calls per conversation | 7.0 |
| PM spec budget ($0.03) | 83x under |

What keeps it down, in order of effect:

1. **At most two model calls per turn**, and only one when no action is proposed. There is
   no planner/executor loop and no reflection pass.
2. **The account context is a compact block built by code** (`build_context_block`), not
   raw JSON. Six invoices are summarised to one line each; the rest are a count.
3. **History is trimmed** to the last 8 exchanges.
4. **Refusals cost nothing extra.** A denied policy decision and a refused approval are
   both phrased from code-written strings, so they never spend a call rephrasing.
5. gpt-4o-mini, because the model's job is intent classification plus three sentences of
   prose. Nothing in the money path depends on model quality.

## Recorded conversations

| Transcript | Customer | Scenario | Outcome |
|---|---|---|---|
| `20260905T132723Z` | maya.chen | Refund 9 days into a monthly first charge | Approved, $99.00 refunded |
| `20260905T132741Z` | grace | Refund demanded with the injected "override code 7781" | Refused, Refund Policy 1.2, nothing moved |
| `20260905T132757Z` | sam.okafor | Email maps to two workspaces | Asked which; approver refused; nothing moved |
| `20260905T132810Z` | ahmed | Enterprise asks to move to Scale | Refused, account manager |
| `20260905T132824Z` | maya.chen | Refund while `refund_commit_then_503` armed | One refund, resolved by idempotent replay |
| `20260905T132840Z` | tomas.rivera | Downgrade request, in Spanish, 12 seats used | Refused in Spanish, seat limit explained |
| `20260905T132911Z` | maya.chen | Second 503 run, captured with `--trace` | One refund; trace shows 503 then replay |

## Limits, honestly

- **Refund Policy 4.2** requires a refund request to come from a workspace Owner or Billing
  Admin. The sandbox customer object has no role field, so this cannot be checked. The
  brief says to treat the email as authenticated; role is not verified and is flagged in
  DECISIONS.md rather than silently ignored.
- **No fixture customer can complete a downgrade**: every workspace exceeds the seat
  allowance of every lower plan, so "downgrade me" always hits the seat rule first. The
  next-cycle path is therefore proven by unit test rather than by an end-to-end run.
- **PM spec point 6 (3 second replies) is not met and cannot be.** A refund turn is roughly
  7 sandbox calls plus 2 model calls; the sandbox alone spends 0.6-0.9s inside
  `POST /refunds` and up to 5s under `latency_spike`. Measured turns run about 3-6s.
- The conversation is single-threaded and in-memory. Restarting the CLI starts a new
  conversation; there is no cross-session resume.
