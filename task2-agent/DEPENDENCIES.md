# DEPENDENCIES.md

Task: Task 2, Billing Helper agent. Every third-party package added, what it does, what I
would have to write without it, and the risk I see.

| Package | Version | What it does here | If it were removed | Risk |
|---|---|---|---|---|
| `langgraph` | 1.1.3 | The conversation state machine: `StateGraph`, typed `ConvState`, conditional edges between the eight nodes in the README diagram. | About 100 lines of dispatch: a node registry, a loop that calls the current node, merges its returned dict into state, and follows a routing function. Genuinely writable — what I would lose is the guarantee that every branch is declared in one place, which is exactly what makes the state diagram trustworthy. | Young API surface; 1.x is recent and edge-definition signatures have moved between versions. Pinned exactly. Contained: only `graph.py` imports it, and `_build` is 20 lines, so replacing it is an afternoon. |
| `langchain-openai` | 1.6.0 | `ChatOpenAI` plus `with_structured_output(TurnPlan, include_raw=True)`, which is how the model returns a typed proposal and how I get `usage_metadata` for the cost report. | The `openai` SDK directly with a JSON schema in `response_format`, plus my own parse-and-validate. Perhaps 40 lines. The `include_raw=True` usage plumbing is the fiddly part. | Two layers between me and the API (LangChain core plus the OpenAI SDK), so a break can come from either. Vendor-shaped: swapping providers means changing this import and nothing else, since `LLM` is the only place it appears. |
| `pydantic` | 2.9.2 | `TurnPlan` and `ProposedAction`: the schema the model must fill in, and the validation that a malformed response cannot become an action. | Hand-written JSON schema plus manual validation of every field before use. Not hard, but this is the boundary where untrusted model output enters the system, so I would rather it be a well-tested library than my own checks. | Very low. Already a transitive dependency of both packages above; pinning it explicitly just makes the version visible. |
| `requests` | 2.34.2 | Every sandbox HTTP call, and the response headers the design depends on: `X-Sandbox-Now`, `Retry-After`, `Idempotent-Replayed`. | `urllib.request` from the standard library. Around 30 extra lines, mostly turning `HTTPError` back into a response object so a 4xx/5xx body can be read — `urllib` raises on error statuses, and this client needs to *read* the 503 body to decide to reconcile. | Very low. Stable for a decade, and used through a single `_request` method. |
| `python-dotenv` | 1.0.1 | Loads `.env` so `OPENAI_API_KEY` is not typed into the shell each run. | Four lines parsing `KEY=value`. | None. Optional at runtime: `chat.py` wraps the import in `try/except ImportError` and works without it. |
| `pytest` | 9.1.1 | The 77 tests, plus fixtures that boot a sandbox on a free port and arm chaos modes. | `unittest`, losing parametrised cases and fixture composition. The chaos tests would get noticeably more verbose. | None. Test-only, never imported by shipped code. |

## Notes

- **Nothing was added for the money path.** `policy.py` imports only `dataclasses`,
  `datetime` and `typing` from the standard library, so the refund rules can be read,
  tested and audited without installing anything. That was deliberate.
- The sandbox itself has zero dependencies. I did not add any to it and did not modify it.
- No package here is doing arithmetic on money. All amounts stay integer minor units and
  are formatted for display only, in `money.py`.
- Total install is dominated by the LangChain stack. If this were a service that had to
  start in milliseconds I would drop `langgraph` and hand-roll the dispatch, as described
  above; at a CLI's cold-start budget it is not worth the loss of explicitness.
