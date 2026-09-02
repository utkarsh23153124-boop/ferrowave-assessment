# Ferrowave Pulse Engineering Assessment

## The three tasks

Ferrowave Pulse is a fictional NPS survey product invented for this assessment. The
attached pack contains its documentation, a sandbox of its billing system, and a survey
export. You have five days and we expect about 18 to 24 hours of work. The full brief in
the pack has the exact interface contracts and submission templates; this page is the
assignment.

### Task 1. Documentation answer engine (RAG)

Build a service that answers customer questions using only the Ferrowave documentation in
the pack: 41 files in Markdown, HTML, CSV, JSON, one PDF, and one Word file, plus a
manifest listing each file's status and audience. Expose `POST /ask` with a question; return
the answer, citations (file path plus the exact quote used), and one of three statuses:
answered, insufficient evidence, or needs clarification. Some documents contradict each
other, some are out of date, some are drafts, some are internal and must never reach a
customer, and some questions cannot be answered from the documents at all. Your system has
to get those cases right.

Hand in: the running service with a one-command start and re-index; your own eval set of at
least 25 questions with results, including the ones it gets wrong; a note on what you
noticed while working with the documents; and your DECISIONS, ITERATIONS, DEPENDENCIES,
and AI_USAGE logs. In the live session we run our own questions against it.

### Task 2. Billing agent inside a code framework

Build a chat agent, using LangGraph, PydanticAI, CrewAI, or a comparable framework, that
handles billing conversations for Ferrowave customers: refund requests, plan upgrades and
downgrades, and "why was I charged this" questions. You get the product manager's spec
exactly as written, and a local sandbox of the billing system (one Python file plus its API
reference) that behaves like the real one, including its failure modes. Three rules override
everything: never move money that policy does not allow, never move it twice, and never
tell a customer something happened that did not. The spec has problems in it; finding them
and documenting how you resolved each one is part of the task.

Hand in: the agent as a command-line chat we can type into, a state diagram of the
conversation, tests covering every failure mode in the sandbox reference, transcripts of
five conversations, the measured cost per conversation, and the four logs. In the live
session we play customers while watching the sandbox ledger of what your agent actually did.

### Task 3. Rapid prototype that then has to change

Part A, time-boxed to 4 hours: build a command-line tool that reads the survey export in
the pack (a CSV of about 350 rows, deliberately messy) and produces a digest for the week
we name: NPS this week versus last week (computed in code, never by a model), the five most
common themes in the comments with counts and example quotes, a short watch-outs section,
and a footer stating how many rows were read, used, and excluded, and why. Tag the commit
`v1` and tell us.

Part B, time-boxed to 3 hours: we send a requirements change only after we receive `v1`.
Implement it, tag `v2`, and write down specifically what in your v1 made each change easy
or hard.

### Rules for all three

Any language, any framework, any tool, any model, hosted or local. We do not provide API
keys, credits, or accounts; every choice and its cost is yours, and every choice must be
justified in writing. We assume you will use AI; we evaluate whether you understood and
directed what it produced, so every task ships with DECISIONS, ITERATIONS, DEPENDENCIES,
and AI_USAGE logs (templates in the pack), including what each task cost you. One
repository per task, runnable from a clean clone with one command. You may send us up to five written questions during
the window. After submission there is a 90-minute live session: we run hidden tests against
your systems, ask you to walk through your decisions from the code, and ask you to make
changes we choose on the spot. Code you cannot modify live counts against you.
