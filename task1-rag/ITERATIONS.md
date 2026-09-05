# ITERATIONS.md

Task: Task 1 (answer engine)

A dated log. Each entry: what I built or changed, what I observed (with evidence), what I
concluded, what I did next.

## Entries

### 2026-09-04 Read the corpus before writing code

- Built or changed: nothing yet. Had every file read end to end, including the PDF via pypdf
  and the Word file via python-docx, and wrote up every contradiction with both quotes.
- Observed (evidence): 26 distinct contradictions, four documents that must never reach a
  customer, one prompt injection in a forum post, and a manifest that calls a 2023 FAQ
  "current". The DPA's sub-processor list exists only in a table that `document.paragraphs`
  does not return. The rate-limit HTML uses `colspan="3"` for the Starter row.
- Concluded: the design has to be metadata-first (manifest as allowlist), precedence has to
  be in code, and every format needs its own loader. Recency ranking is actively harmful
  here (the draft SLA is the newest SLA document).
- Next: policy module and loaders first, retrieval second, model last.

### 2026-09-04 Loaders: two bugs found by printing every chunk

- Built or changed: nine loaders in `rag/loaders.py`, then printed every chunk of the seven
  tricky files.
- Observed (evidence): Enterprise rendered as "Price: not offered per month or not offered
  per year" because `monthly_usd_minor: null` took the extra-seat wording. Everything else
  came out as intended: Starter row expanded across three columns, the burst note kept from
  `tfoot`, the sub-processor table under Annex 3, the injection block gone with the post
  flagged, PDF clauses on their own lines.
- Concluded: rendering JSON to prose is right, but every null needs its own wording.
- Next: fixed the price wording, pinned it in `tests/test_loaders.py`.

### 2026-09-04 First end-to-end run: the model ignored the tier rule

- Built or changed: retrieval (BM25 + FAISS, tier-weighted) and the answer layer with the
  first system prompt, which put the authority tier in each chunk header and told the model
  the lower number wins.
- Observed (evidence): on "Do you offer a 30-day money-back guarantee?" the answer was "Yes,
  we offer a 30-day money-back guarantee on all plans, no questions asked", cited from
  `support/faq.md` (tier 5). `policies/refund-policy.md` (tier 1) was in the context at
  positions 3 and 5. Seven of eight trap questions were right; this one was wrong in the
  most customer-damaging way possible.
- Concluded: a tier number in a header is not enough when a low-tier chunk echoes the
  question's wording. Position and explicit warnings matter more than a rule in the prompt.
- Next: context is now sorted by tier before the score, chunks with tier 4 or worse or a
  pre-2025 date carry a `WARNING:` line, and the prompt rule says "always, even if the
  lower-authority chunk matches the question's wording better". Reran: refund answered
  from the policy with both the 14-day and 30-day terms. Stayed correct in both full evals.

### 2026-09-04 Plan gate too eager

- Built or changed: `policy.plan_gate`, a regex list that forces `needs_clarification` when
  a plan-dependent topic is asked without a plan.
- Observed (evidence): "Which channels can I use to deliver a survey?" (one of the brief's
  own sample questions, answer identical on every plan) was forced to clarification by a
  `can i (use|get|add)` pattern. "What uptime does the SLA commit to?" was forced by `sla`.
- Concluded: the gate should cover only facts that are actually a per-plan table (seats,
  price, quota, rate limit, retention, support target). Anything softer belongs to the model.
- Next: cut five patterns and the SLA one. Side effect, kept deliberately: Q28 ("Can I get a
  refund for my subscription?") and Q29 ("Can I use webhooks?") now come back `answered`
  with a conditional answer instead of a question. Both recorded as failures in EVAL.md.

### 2026-09-04 First full eval: 36/40, and a flaky citation on Q04

- Built or changed: `eval/questions.jsonl` (40 questions) and `eval/run.py`.
- Observed (evidence): 36 pass. Q04 "What is the target support response time on the Growth
  plan?" came back `insufficient_evidence` with diagnostics notes "answered without a
  verifiable citation; downgraded" and "1 citation(s) dropped". The right chunk
  (`plans-and-features.md` > Support) was retrieved first and the model's private reason
  said "clearly supported by the product documentation". I could not see the rejected quote
  because the guard did not log it. Reran Q04 alone: pass, one call, verbatim quote.
- Concluded: two problems. No observability on the guard, and a correct answer can be lost
  to one bad quote plus one bad repair. Temperature 0 is not deterministic.
- Next: rejected quotes are now in `diagnostics.notes`. Added `fallback_citation`: when the
  model's quotes fail twice, code picks the retrieved sentence with the best content-token
  overlap with the answer (stopwords removed, plurals stripped, threshold 0.5) and verifies
  it against the file like any other quote. First version used a 0.6 threshold and missed
  the Q04 sentence at 8 of 14 tokens because "day" and "days" did not match; hence the
  stemming. Second full eval: 37/40, Q04 passing, fallback not needed on that run.

### 2026-09-04 What did not work: shell edits with backslashes

- Built or changed: two small edits through the shell, one `sed`, one Python heredoc.
- Observed (evidence): both wrote a literal newline where `\n` was intended. The test file
  failed collection with "unterminated string literal", and `rag/answer.py` briefly had a
  broken regex on line 107, which made every import fail.
- Concluded: the tool path un-escapes backslashes. Nothing to do with the system, but for
  ten minutes "tests pass" would have been false.
- Next: used the editor tool for anything containing a backslash; tests back to 17 passing.

### 2026-09-05 Audit of the finished service

- Built or changed: nothing at first. Cloned the repo fresh into a new virtualenv and ran
  install, ingest, tests and an eval subset from the README alone; then ran a multi-angle
  code review over the Task 1 commits and reproduced each finding against the real corpus.
- Observed (evidence), the ones that mattered:
  - `write_index` deleted `index/` before calling the embeddings API. With no key (this
    build machine until yesterday) or a network error, the service could not start again
    until someone ran ingest by hand. `POST /reindex` had the same failure mode.
  - The plan gate's `\b(eu|european|us|region ...)\b` pattern matched the pronoun "us":
    "Which events can webhooks send to us?" was forced into clarification. `cost` and
    `how much` matched "How much notice do you give". Lowercase "scale" in "at scale" made
    the gate think a plan was named, disabling it.
  - The fallback citation picked the best-overlapping sentence from any retrieved chunk.
    For "Do you offer a 30-day money-back guarantee?" with a correct "No" answer, the best
    overlap was the stale FAQ's "We offer a 30-day money-back guarantee on all plans": a
    verbatim, visible citation asserting the opposite of the answer.
  - The repair call did not include the model's first draft in the transcript, and its
    acceptance rule compared citation counts only, so a repair that returned
    `insufficient_evidence` with no citations replaced a correct answer.
  - The plan gate override was applied even when the model said the corpus had nothing,
    producing "Which plan are you on? I could not find that in the documentation".
  - `/reindex` accepted any filesystem path and no authentication.
  - The forum loader's synthetic header ("Post by X (staff), date:") was written into the
    extracted text and could therefore pass quote verification although it is not in the
    document. The manifest's `supersedes` column was carried on every chunk and read nowhere.
  - Q23's blog quote failed verification because the model closed it with a full stop the
    source line does not have; the repair did not fix it; the (first version of the)
    fallback refused tier 4, so a correct answer was downgraded.
  - A Windows-only one: pip could not install lxml in a clone under a deep path because of
    the 260-character limit. Not a repo bug, but a reviewer could hit it.
- Concluded: every one of these is a case where a guardrail meant to add safety could
  remove a correct answer or add a wrong citation. The guardrails needed guardrails.
- Next: build into a temp dir and swap atomically, refuse to delete non-index directories,
  degrade to BM25 without a key instead of failing; rewrite the gate patterns and require a
  plan to be a proper noun or next to "plan"; restrict the fallback to documents the model
  cited, tiers 1-4, never stale; keep the first draft unless the repair strictly improves
  it with the same status; force clarification only over an `answered` draft; restrict
  `/reindex` to paths inside the repo with an optional token; verify prose formats against
  the raw file only; honour `supersedes`; forgive trailing punctuation on quotes and return
  the trimmed form; preload verification text into memory so a concurrent reindex cannot
  race it. 29 tests pass (10 new). Eval 37/40 before and after, but the new run needs zero
  repair calls and zero guardrail overrides; the old one needed two repairs.

### 2026-09-04 Things I tried and dropped

- Letting the model decide on every plan-dependent question with no gate: it answered
  "How many seats do I get?" with the full per-plan table as `answered`. Helpful text,
  wrong status under the contract. The gate stays.
- Skipping hidden documents at ingest instead of filtering at retrieval: simpler, but then
  a live-session "show me what the draft SLA chunks look like" needs a rebuild. Filtering
  costs nothing and keeps the chunks inspectable.
