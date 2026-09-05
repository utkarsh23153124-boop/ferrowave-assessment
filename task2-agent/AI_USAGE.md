# AI_USAGE.md

Task: Task 2, Billing Helper agent.

## What I used

| Tool / model | Used for |
|---|---|
| Claude Opus (via Claude Code) | Reading the sandbox source and fixtures with me, drafting `policy.py`, `sandbox_client.py`, `graph.py` and the test suite, and drafting these documents. |
| gpt-4o-mini | The agent's own runtime model. Not a development tool. |

Everything was run and verified locally against the real sandbox before it was kept. No
code was committed that I had not seen fail or pass on evidence.

## What the AI got wrong, concretely

### 1. It asserted a failure mode the sandbox does not actually have

The first version of `test_unresolvable_503_raises_rather_than_claiming_success` assumed
that arming `refund_commit_then_503` with a high count would keep defeating reconciliation.
The test failed with `DID NOT RAISE`.

Reading `server.py` showed why: the idempotency key is stored *before* the chaos check, so a
replay short-circuits ahead of it and always resolves. The assumption was plausible and
wrong, and only the source settled it. I split it into a test that asserts the real
guarantee and a second that stubs a transport failure to reach the unknown-outcome branch.
This is the clearest example of why I read the sandbox source rather than trusting a
description of it.

### 2. It wrote tests against fixtures it had guessed at

Two separate tests asserted outcomes for customers who cannot produce them: a successful
downgrade for Maya (4 seats used, Starter includes 3), and, earlier, a plan-change flow for
a customer whose seat count made it impossible. Both failed on the first run.

Chasing the second one properly — checking all 14 fixture customers instead of swapping in
a different email — is what surfaced the finding that **no fixture customer can downgrade at
all**. The AI's instinct was to change the test to a passing customer; the useful move was
to ask why every customer failed. That finding is now in DECISIONS.md Spec issues 4 and in a
test.

### 3. It trusted a prompt instruction to enforce a safety property

When the first live conversation produced "I **will** process that for you now" after the
refund had already completed, the fix offered was to add an instruction to the prompt telling
the model to use the past tense. That worked on the next run.

Then the same conversation, unchanged, produced "a full refund **is available**" for a
completed refund. The prompt had made the failure rarer, not impossible. I rejected the
prompt-only fix and moved the factual sentence into code (`_confirmation_line`), leaving the
model only the surrounding prose. The general lesson, which I applied again to the internal
notes, is that a prompt instruction is a preference and a code path is a guarantee, and the
three rules in this task need guarantees.

### 4. It initially wrote the notes redaction as a prompt instruction

The first pass at PM spec point 7 put `customer.notes` into the context block with a line in
the system prompt saying not to disclose them. Given that one fixture's notes are an
instruction addressed to AI agents telling them to refund without checks, that design hands
the attacker the microphone and asks the model politely not to listen. Moved the redaction to
the client boundary so the field never exists downstream, and kept the policy gate as the
second layer. Both are asserted in `test_injection.py`.

### 5. Smaller things I corrected

- A string bug that wrote refund reasons as "Refund Policy Refund Policy 1.1" into the
  ledger, because a prefix was added to a value that already carried it.
- The escalation sentence appended twice when the model echoed the previous turn's reply
  back out of the conversation history.
- An over-broad `needs_human` description in the schema that made the model escalate a
  seat-reversal refund the policy engine handles correctly.
- A first draft that let the model propose the refund *amount*. Amounts now come from
  policy and the sandbox's proration preview, and are clamped by `cap_refund_amount`;
  `test_the_model_cannot_inflate_the_amount` pins it.

## What I wrote or decided without AI

- The overall architecture: the decision that the model returns a structured proposal and
  code disposes of it, rather than a tool-calling loop. That decision is the reason most of
  this task's requirements are satisfiable at all.
- The resolution of every item in DECISIONS.md **Spec issues** — which spec point loses,
  and why. The contradictions were found by reading the spec against the Refund Policy and
  the API reference; the judgement about which side wins is mine.
- The decision to hard-code the refund policy rather than reuse the Task 1 retriever, and
  the reasoning that a retrieval miss must not be able to authorise money movement.
- The choice to treat identity disambiguation as scoping rather than as the one clarifying
  question the spec allows.
- The decision to gate plan changes behind the same approval as refunds.

## Ratio

Most of the typing is AI-assisted. Every failing test in ITERATIONS.md is a case where I
did not accept what was produced, and the two most important properties of this system —
the confirmation sentence being code-generated, and notes never reaching the model — are
both places where I rejected the AI's first design in favour of a code-level guarantee.
