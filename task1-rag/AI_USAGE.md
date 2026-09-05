# AI_USAGE.md

Task: Task 1 (answer engine)

## Tools and models used

| Tool or model | Used for |
|---|---|
| Claude (Claude Code, in the editor) | Reading the whole corpus and producing the first contradiction inventory; drafting loaders, retrieval, answer layer, tests and the eval runner; drafting these documents from my notes. |
| OpenAI `gpt-4o-mini` | The production model behind `/ask`: drafts the answer, status and citations under the guardrails in `rag/answer.py`. |
| OpenAI `text-embedding-3-small` | Dense retrieval vectors for the FAISS half of the hybrid retriever. |

## At least three things an AI produced that were wrong or that I changed

1. **The first system prompt trusted the model to apply precedence, and it did not.**
   - What it produced: a prompt rule saying "lower tier number wins" with tiers in each chunk
     header. On "Do you offer a 30-day money-back guarantee?" the model answered "Yes, on
     all plans, no questions asked" from the 2023 FAQ (tier 5) while the refund policy
     (tier 1) sat three chunks lower in the context.
   - What I did instead: context is now sorted by authority before it reaches the model,
     stale and low-tier chunks carry an explicit warning line, and the prompt says a
     low-authority chunk must not be cited when a tier 1 to 3 chunk covers the topic.
   - How I knew: I ran the eight trap questions from CORPUS_NOTES before the eval set existed.
     The refund answer was wrong on the first run and right on every run since.

2. **The plan gate regex was too eager.**
   - What it produced: patterns like `can i (use|get|add)` and `sla` meant "Which channels
     can I use to deliver a survey?" (plan independent) and "What uptime does the SLA
     commit to?" (answerable with scope) were forced into `needs_clarification`.
   - What I did instead: cut the list to numeric plan facts (seats, price, quota, rate limit,
     retention, support target) and let the model handle the rest. Two eval questions (Q28,
     Q29) now come back `answered` where I expected clarification; I kept them in the eval
     as documented soft spots rather than widening the regex again.
   - How I knew: unit test for `plan_gate` on the brief's sample questions.

3. **The citation guard was downgrading correct answers.**
   - What it produced: an answer that is "answered" but whose quotes fail verification (even
     after the repair round trip) was turned into `insufficient_evidence`. On the first full
     eval, Q04 (Growth support response time) was retrieved correctly, answered correctly,
     and then thrown away because the model's quote was not verbatim, and the repair did not
     help. The same question passed on the next run, so this was model nondeterminism.
   - What I did instead: `fallback_citation` picks the retrieved sentence with the highest
     token overlap with the answer (threshold 0.6). It is verbatim by construction and is
     still checked against the file. Diagnostics say when code chose the citation.
   - How I knew: `diagnostics.notes` now records rejected quotes; it was empty before, which
     is itself a thing the AI draft got wrong (no observability on the guard).

4. **The Enterprise plan rendered as "Price: not offered per month".**
   - What it produced: the JSON loader treated `monthly_usd_minor: null` the same as a
     missing key and printed the "not offered" wording meant for extra seats.
   - What I did instead: null price now renders as "custom, quoted by sales". Pinned by a
     loader test.

5. **The AI-drafted guardrails could remove correct answers.** A code review run over the
   finished service (itself AI-assisted, findings reproduced by me against the corpus)
   showed the fallback citation could attach the stale FAQ's "30-day money-back" sentence
   to an answer that said the opposite, the repair pass could swap a correct answer for a
   refusal, and the rebuild deleted the working index before the network call that could
   fail. Each is in ITERATIONS 2026-09-05 with the fix and a test. The lesson I took: a
   guard written to catch the model's mistakes needs the same scrutiny as the model.

6. **`sed` on Windows inserted a literal newline into a test file.** Not an AI mistake as
   such, but the assistant's shell edit broke the suite; fixed with an editor tool. Noted
   because "the tests were green" would have been false for ten minutes.

## Parts I wrote or designed without AI assistance

- The authority tier table and the stale-document penalty in `rag/policy.py`, and the
  decision to mirror ToS s.14.1 rather than invent an ordering.
- The decision to index hidden documents but filter at retrieval (so a reviewer can inspect
  chunks and a live-session "un-hide this" change is one line), rather than skipping them
  at ingest.
- The eval set design: which traps to include, which questions are deliberately debatable,
  and the three leak probes.
- The list of corpus fixes in CORPUS_NOTES section 7.

## Prompts or instructions I found necessary to get useful output

- "Chunks are listed highest authority first ... the LOWER tier number wins, always, even if
  the lower-authority chunk matches the question's wording better." Without "always" and
  the wording clause, the model kept preferring the chunk that echoed the question.
- The structured output schema with a `reason` field the customer never sees. Reading
  `model_reason` in diagnostics is how I found that the model believed it had answered Q04.
- For the corpus survey: "Read EVERY file fully ... quote both sides with file paths and the
  exact conflicting numbers." Asking for quotes rather than summaries is what made the
  contradiction table checkable.
