# Task 1: Ferrowave documentation answer engine

A retrieval-augmented service that answers customer questions from the 40 documents in
`corpus/`, cites verbatim quotes, and says when it should not answer.

## Quick start

```bash
cd task1-rag
pip install -r requirements.txt
cp .env.example .env           # put your OPENAI_API_KEY in it (or export it in the shell)
python ingest.py --corpus ../corpus     # build the index (about 10 seconds, under $0.001)
python app.py                            # serve on http://127.0.0.1:8000
```

Ask a question:

```bash
curl -s http://127.0.0.1:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "How many seats are included on the Scale plan?"}'
curl -s http://127.0.0.1:8000/health
```

Without the server: `python ask.py "Which events can webhooks send?"`

## Re-index

```bash
python ingest.py --corpus /path/to/other/corpus     # then restart app.py
# or, while the server runs:
curl -s -X POST http://127.0.0.1:8000/reindex -H "Content-Type: application/json" -d '{"corpus": "../corpus"}'
```

`--no-embed` builds a BM25-only index with no network calls, and ingest does the same on
its own when `OPENAI_API_KEY` is not set. Retrieval quality drops in that mode (dense
retrieval is what surfaces the refund policy for "money-back guarantee"), and answering
still needs the key. A rebuild happens in a temporary directory and is swapped in only when
complete, so a failed rebuild never removes the working index.

`POST /reindex` only accepts corpus paths inside the repository. Set `RAG_ADMIN_TOKEN` in
the environment to also require an `X-Admin-Token` header.

## Eval and tests

```bash
python eval/run.py --direct        # in-process, writes eval/results.md and eval/results.jsonl
python eval/run.py                 # same, but through the running HTTP service
python -m pytest                   # offline tests: loaders, policy, ingest, quote verification
```

`EVAL.md` summarises the latest run, including the questions it gets wrong.

## Interface

`POST /ask` body `{"question": "..."}` returns

```json
{"answer": "...", "status": "answered | insufficient_evidence | needs_clarification",
 "citations": [{"path": "policies/refund-policy.md", "quote": "verbatim, max 300 chars"}],
 "confidence": 0.9,
 "diagnostics": {"latency_ms": 2500, "model": "gpt-4o-mini", "tokens_in": 1700, "tokens_out": 90,
                 "estimated_cost_usd": 0.0003, "llm_calls": 1, "retrieved": [...], "plan_gate": "open", "notes": []}}
```

`GET /health` returns `{"ok": true, "documents_indexed": 36, "model": "gpt-4o-mini", ...}`.
`documents_indexed` counts documents customers may see; four more are indexed but hidden.

## How it works

```
corpus/_manifest.csv  ->  rag/ingest.py  ->  index/            (chunks.jsonl, faiss/, extracted/)
                            | rag/loaders.py   one loader per format, each handling a known trap
                            | rag/policy.py    authority tier + customer visibility per document
POST /ask  ->  rag/retrieve.py  BM25 + FAISS (LangChain EnsembleRetriever) over visible chunks,
           |                     fused rank re-weighted by authority tier
           ->  rag/answer.py    gpt-4o-mini with structured output, then code guardrails:
                                 plan gate, verbatim quote check, hidden-doc check, downgrade
```

**Ingestion is manifest-driven.** A file not listed in `_manifest.csv` is not indexed. Each
chunk carries the manifest row (audience, status, last_updated, notes) so the rest of the
pipeline never re-reads it.

**Customer visibility** (`policy.customer_visible`): `audience != public` or
`status in {draft, superseded}` means the document is indexed for inspection but never
retrieved, never shown to the model, and rejected if the model somehow cites it.

**Precedence** (`policy.tier_for`): legal, policies and pricing are tier 1; product docs and
release notes tier 2; help centre and trust pages tier 3; blog and marketing tier 4;
community threads tier 5. A document last updated before 2025 drops two tiers, which is
what pushes the 2023 FAQ below the blog. The fused retrieval score is multiplied by a
per-tier weight, the context is presented highest tier first, and low tier or stale chunks
carry a warning line. This mirrors the order of precedence in the Terms of Service s.14.1.

**Status** is decided by the model, then overridden by code in three cases:

- the question hits a plan-dependent topic (seats, price, quota, rate limit, retention,
  support target) without naming a plan: forced to `needs_clarification`;
- `answered` with no citation that survives verification: downgraded to `insufficient_evidence`;
- any citation whose quote is not verbatim in the file, or whose path is not customer
  visible, is dropped (one repair round trip is attempted first).

**Quote verification** normalises whitespace and markdown emphasis and checks the quote
against the raw file for text formats, or against the extracted text for PDF, Word, HTML
tables and JSON (where "verbatim" means verbatim in what the loader produced).

**Prompt injection**: `[[...]]` blocks in forum posts are stripped at ingest, forum posts
are chunked one per post with the author role, and the system prompt treats all chunk
content as data. The eval set includes an injected question (Q40).

## Windows note

Deep clone paths can hit the 260-character path limit when pip installs lxml. Clone into a
short path (for example `C:\src\ferrowave`) or enable long paths in Windows.

## Live session

Expose the service with `ngrok http 8000` or `cloudflared tunnel --url http://127.0.0.1:8000`.
Swapping the corpus is `python ingest.py --corpus <path>` plus a restart, or `POST /reindex`.

## Measured numbers

See `EVAL.md` for the latest pass rate, p50/p95 latency and cost per question.
