# Ferrowave Pulse Engineering Assessment

## Candidate brief

Thank you for taking the time to do this. It is a take-home assessment with three tasks
built around one fictional company, Ferrowave Ltd, and its product, Ferrowave Pulse (an
NPS and customer feedback platform). Ferrowave does not exist; every document, customer,
and number in this pack is invented for the assessment.

The tasks are the kind of work you would do here in your first months: a retrieval-backed
answer engine over messy documentation, a purpose-built agent that touches money, and a
fast prototype that then has to survive a requirements change.

## 1. How this works

**Window.** You have five calendar days from the day you receive this pack. Tell us if
something comes up; we would rather extend than receive rushed work.

**Effort.** We expect 18 to 24 hours of focused work across all three tasks. If you run
out of time, submit what you have with an honest status. A partial submission with clear
reasoning is worth more to us than a complete one that you cannot explain.

**Order.** Do Task 3 (the prototype) whenever you like, but read the Task 3 instructions
carefully: it has a Part A and a Part B, and Part B is only sent to you after you submit
Part A. Plan for that.

**AI tools.** You may use any AI coding tool, assistant, or model. We assume you will. What
we evaluate is whether you understood, tested, and directed what was produced. Every task
requires an `AI_USAGE.md` describing what you used, for what, what it got wrong, and what
you changed. There is no penalty for heavy AI use and there is no credit for avoiding it.
There is a penalty for submitting something you cannot explain.

**The live session.** After submission we will schedule a 90-minute video session. In it
we will run our own questions and scenarios against your systems, ask you to walk through
your decisions, and ask you to make changes to your code while we watch. The changes are
chosen by us on the day. Code you cannot modify live counts against you, however good it
looks on paper.

**Questions.** You may send us up to five written questions during the window. We answer
within one business day. Some answers will be "decide, document your assumption, and move
on". That is a real answer; part of the job is working with incomplete specifications.

**Honesty.** If you did not finish something, say so. If a number in your report is an
estimate, label it. If your eval results were cherry-picked, do not report them. We check.

## 2. Ground rules that apply to every task

- One git repository per task (or one monorepo with three top-level folders). Commit as
  you go. Your commit history is part of the submission; we read it.
- Any language, any framework, any tool, any model, hosted or local. We do not provide
  API keys, credits, accounts, or hardware; every choice and its cost is yours. The
  condition is that every choice must be justified in writing in `DECISIONS.md` (see
  templates in Section 7): language, framework or no framework, model, embedding, vector
  store, hosting, and each library. "It is what I know" is an acceptable reason if you say
  so and add what you would choose if starting a team from scratch. If you use a large
  hosted model, justify the cost; if you use a small or local model, justify the quality
  trade-off. Choices you cannot defend in the live session count against you.
- Runnable with one documented command after cloning, plus `.env.example` for secrets.
  Never commit real keys.
- Report what each task actually cost you: model spend in USD with the arithmetic (tokens
  in, tokens out, price per million), or wall-clock time and hardware if you ran locally.
  Estimates must be labelled as estimates.
- Four short documents per task, using the templates in Section 7: `DECISIONS.md`,
  `ITERATIONS.md`, `DEPENDENCIES.md`, `AI_USAGE.md`. These are not optional and they are
  read before the code.
- Tests where the brief asks for them. We run them.
- Write plainly. This is not a writing test, but we need to follow your reasoning.

## 3. Task 1: Answer engine over the Ferrowave corpus

### Context

Ferrowave wants a customer-facing assistant that answers questions about the product,
pricing, and policies from its own documentation. The documentation is in
`corpus/`: 41 files in Markdown, HTML, CSV, JSON, plain text, one PDF, and one Word
document, plus `_manifest.csv` describing each file. The corpus is what a real company's
documentation looks like. Read it before you index it.

### What to build

A retrieval-augmented answer service that answers questions using only the corpus, cites
what it used, and knows when it should not answer.

### Interface contract (we test against this)

`POST /ask` with body `{"question": "..."}` returns JSON:

```
{
  "answer": "string, plain prose, customer facing",
  "status": "answered" | "insufficient_evidence" | "needs_clarification",
  "citations": [{"path": "policies/refund-policy.md", "quote": "verbatim text, max 300 chars"}],
  "confidence": 0.0 to 1.0 or null,
  "diagnostics": {"latency_ms": int, "model": "string", "tokens_in": int, "tokens_out": int,
                  "estimated_cost_usd": float}
}
```

- `answered`: the corpus supports the answer.
- `insufficient_evidence`: the corpus does not contain enough to answer. The `answer`
  field should say so and, where helpful, say what the corpus does cover.
- `needs_clarification`: the question cannot be answered without knowing something about
  the asker (for example, which plan they are on). The `answer` field should ask.

`GET /health` returns `{"ok": true, "documents_indexed": int, "model": "string"}`.

A documented command rebuilds the index from a corpus path, so we can re-index if we swap
in a modified corpus during the live session.

### Requirements

1. Citations must point at real files in `corpus/` with quotes that actually appear in
   them.
2. The assistant is customer facing. Decide what that means for documents in the corpus
   and document the decision.
3. When documents disagree, your system needs a way to decide which one wins. Document it.
4. Latency target: median under 8 seconds per question. Report your measured p50 and p95.
5. Report estimated cost per question.

### What to submit

- The service, with a one-command run and a one-command re-index.
- `EVAL.md`: at least 25 questions you wrote yourself, with the expected answer, the
  expected status, and your system's actual result on each. Include questions your system
  gets wrong. A 25/25 result with no discussion will be treated as a sign that the eval set
  is too easy, not that the system is good. Put the questions in `eval/questions.jsonl` and
  the runner in `eval/run.py` (or equivalent) so we can re-run it.
- `CORPUS_NOTES.md`: what you noticed about the corpus while working with it. Anything
  that surprised you, anything you had to handle specially, anything you think Ferrowave
  should fix in its documentation.
- `DECISIONS.md`, `ITERATIONS.md`, `DEPENDENCIES.md`, `AI_USAGE.md`.

### Sample questions

These are not the questions we will test with. They show the shape.

- Which channels can I use to deliver a survey?
- How many seats are included on the Scale plan?
- How long are export files available for download?
- What is the target support response time on the Growth plan?
- Which events can webhooks send?

### What we look at

Whether the system prefers the right document when two disagree. Whether it says "I do
not know" when it should. Whether it can be trusted in front of a customer. Whether your
own eval set found real weaknesses. Whether you can explain, in the live session, why the
chunking, retrieval, and prompting are the way they are and what you tried first.

## 4. Task 2: Billing Helper, a purpose-specific agent

### Context

Ferrowave's product manager wants a chat agent that handles billing conversations for
customers. Below is the spec as we received it. It is reproduced as written.

### Product spec (as received from the PM)

> **Billing Helper v1**
>
> Goal: customers resolve refund requests, plan changes, and "why was I charged" questions
> in chat, without waiting for support.
>
> 1. Handles refund requests, upgrades, downgrades, and invoice questions for all four
>    plans including Enterprise.
> 2. Refunds inside the policy window (30 days on all plans) are processed automatically
>    so the customer does not have to wait.
> 3. A human must approve every refund before money moves.
> 4. Never ask the customer more than one clarifying question per conversation. Customers
>    hate being interrogated.
> 5. Downgrades take effect immediately. Customers hate waiting for the next cycle.
> 6. Every reply is delivered within 3 seconds end to end.
> 7. Use the customer's account notes to personalise the conversation. Never disclose
>    internal notes or any other customer's data.
> 8. Reply in the customer's language.
> 9. Model spend under USD 0.03 per conversation.
> 10. Log every tool call so finance can audit what the agent did.
> 11. When unsure, escalate to a human rather than guess.

### What you are given

- `sandbox/`: a local stand-in for the billing system, with `API_REFERENCE.md`. Run it
  with `python3 sandbox/server.py`. It reproduces the real system's behaviours, including
  its failure modes, and it has chaos controls so you can test them. Read the reference
  fully. Read the server source if you want to.
- The Ferrowave Refund Policy and related documents in `corpus/` (Task 1). Whether you
  reuse your Task 1 retriever, hard-code the policy, or do something else is a design
  decision we want to see reasoned about.

### What to build

A conversational agent built with an agent framework (LangGraph, PydanticAI, CrewAI,
AutoGen, or a comparable orchestration library; if you choose something else, justify it)
that conducts the conversation, calls the sandbox, and acts within policy.

### Interface contract (we test against this)

A command-line chat:

```
<your command> chat --email <customer email> [--sandbox http://127.0.0.1:8787] [--trace]
```

- The customer is identified by email, which you may treat as already authenticated.
- We type as the customer. The agent replies in the terminal.
- `--trace` prints every tool call with arguments and results as they happen.
- If your design includes human approval, the approval prompt appears in the same
  terminal and we will act as the approver.
- On exit, the agent writes `transcripts/<timestamp>.json` containing every turn, every
  tool call with arguments and results, and token usage.

### Requirements

1. The agent must never move money it should not, must never move money twice, and must
   never tell the customer something happened that did not. Design for the failure modes
   in the sandbox reference.
2. `DECISIONS.md` must contain a section titled **Spec issues** listing every point in
   the PM spec that you found ambiguous, contradictory, impossible, or in conflict with
   the policy documents, and how you resolved each. We will compare your list with ours.
3. A state diagram of the conversation flow (any format, ASCII is fine) in the README.
4. Tests, including at least one for each chaos mode in the sandbox reference and one for
   the case where the same email maps to more than one customer.
5. A cost report: measured model spend for at least five conversations, and what you did
   to keep it down.

### What we look at

Whether the agent survives the sandbox's failure modes. Whether policy is enforced by
code or by hoping the model behaves. Whether the framework is doing something for you
that you can name, or is decoration. Whether you found the problems in the spec. In the
live session we will run our own customers and our own failures against your agent, with
the sandbox ledger open.

## 5. Task 3: Weekly Insights Digest, a rapid prototype in two parts

### Context

Ferrowave wants to email customers a weekly digest of what their respondents are saying.
Product wants to see a prototype fast, and then iterate.

### Part A (time box: 4 hours, then tag `v1`)

Build a command-line tool:

```
<your command> digest --input task3_data/responses_sample.csv --week 2026-08-17 --out digest.md
```

It reads the survey export (`task3_data/responses_sample.csv`, about 350 rows over three
weeks) and produces a digest for the requested week (Monday to Sunday) containing:

1. Headline NPS for the week, the previous week's NPS, and the change. NPS is computed
   as the percentage of promoters (score 9 or 10) minus the percentage of detractors
   (score 0 to 6). Arithmetic must be done in code, never by a model.
2. The five most common themes in free-text comments, each with a count and one or two
   representative comments.
3. A short "watch-outs" section: anything the team should look at this week.
4. A data-quality footer: how many rows were read, used, and excluded, and why.

Constraints: total model spend under USD 1 for the sample file; the tool must not crash on
any row in the file; output as Markdown or HTML.

When Part A is done, tag the commit `v1`, push, and email us the tag. Do not continue
until you hear back. Do not spend more than the time box; a rough v1 is expected.

### Part B (time box: 3 hours, then tag `v2`)

We send Part B after we receive your `v1` tag. It changes the requirements. That is the
point of the exercise. You will be asked to describe, specifically, what in your v1 made
the changes easy or hard.

### What to submit

The repository with tags `v1` and `v2`, the four documents, the generated digests, and
tests where Part B asks for them.

### What we look at

Whether v1 handled the data it was given rather than the data it wished it had. Whether
the structure of v1 survived Part B. Whether you know where the numbers come from.

## 6. The live session (90 minutes)

1. Ten minutes: you walk us through the architecture of each task from the code, not
   from slides.
2. Twenty minutes: we run our hidden question set against Task 1 and discuss failures as
   they happen.
3. Twenty minutes: we run hidden customer scenarios against Task 2 with the sandbox ledger
   open.
4. Twenty-five minutes: you make one or two changes we choose, live, in any task.
5. Fifteen minutes: questions about rationale, trade-offs, and what you would do next.

Bring your development environment ready to run. Everything runs on your machine with
your own keys. To let us run our hidden question set against Task 1 and read the sandbox
ledger for Task 2, expose your Task 1 service and the sandbox over a temporary tunnel
(ngrok, cloudflared, or an SSH tunnel) at the start of the session; if that is not
possible, we will dictate the questions and customer messages and you will run them on
screen share. Nothing in the session requires anything you have not already built.

## 7. Submission checklist and templates

### Checklist

- [ ] Repository link(s) with access granted to the address we gave you
- [ ] One-command run instructions verified on a clean clone
- [ ] Task 1: service, `EVAL.md`, `eval/`, `CORPUS_NOTES.md`
- [ ] Task 2: agent, tests, state diagram, cost report, transcripts of at least five
      conversations
- [ ] Task 3: tags `v1` and `v2`, digests in `outputs/`
- [ ] For every task: `DECISIONS.md`, `ITERATIONS.md`, `DEPENDENCIES.md`, `AI_USAGE.md`
- [ ] Cost report per task (spend with arithmetic, or wall-clock and hardware)
- [ ] A list of anything not finished, with what you would do next

### Templates

The `templates/` folder contains these four files. Copy them into each task.

**DECISIONS.md.** One entry per significant decision: language and runtime, framework or
no framework, model choice, chunking and retrieval strategy, policy enforcement approach,
data handling. For each: the options you considered, the one you chose, why, what would
make you reverse it, and what it cost you (time, money, complexity). For Task 2, a
section titled Spec issues is mandatory.

**ITERATIONS.md.** A dated log of what you built, what broke or underperformed, what you
changed, and what evidence told you it was better. Failures are expected here. An
iterations log with no failures will be read as an iterations log that was written
afterwards.

**DEPENDENCIES.md.** A table of every third-party package you added: what it does for
you, what you would have to write if it were removed, and any risk you see (size,
maintenance, licence, lock-in). We will ask about entries at random.

**AI_USAGE.md.** Which tools and models you used, for what, at least three concrete
examples of something an AI produced that was wrong or that you changed and why, and
which parts of the submission you wrote without AI. We do not score the ratio; we score
whether you were in charge.

Good luck. Take the time to read the corpus and the sandbox reference before you write any
code; most of what matters is in them.
