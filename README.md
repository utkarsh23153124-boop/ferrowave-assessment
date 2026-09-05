# Ferrowave Pulse Engineering Assessment: candidate pack

Start with `CANDIDATE_BRIEF.md`. It explains the three tasks, the rules, and what to
submit.

```
CANDIDATE_BRIEF.md      the assessment (also provided as a Word document)
corpus/                 Task 1: 41 Ferrowave documents plus _manifest.csv
sandbox/                Task 2: billing sandbox (server.py, fixtures.json, API_REFERENCE.md)
task3_data/             Task 3: responses_sample.csv
templates/              DECISIONS.md, ITERATIONS.md, DEPENDENCIES.md, AI_USAGE.md, EVAL_FORMAT.md
```

Everything here is fictional. Ferrowave Ltd, Ferrowave Pulse, and every person, customer,
company, price, and policy in this pack were created for this assessment.

Quick checks:

```
python3 --version                 # 3.9 or newer for the sandbox
python3 sandbox/server.py         # starts the billing sandbox on http://127.0.0.1:8787
curl http://127.0.0.1:8787/health
```

Read `corpus/_manifest.csv` and `sandbox/API_REFERENCE.md` before writing code.

---

## Candidate Solutions (Monorepo)

| Task | Folder | Status |
|---|---|---|
| Task 1, documentation answer engine (RAG) | `task1-rag/` | built: service, eval (40 questions), 29 tests, four logs; see `task1-rag/README.md` |
| Task 2, billing agent | `task2-agent/` | built: LangGraph CLI chat, 77 tests, state diagram, 7 transcripts, cost report, four logs; see `task2-agent/README.md` |
| Task 3, weekly insights digest CLI | `task3-digest/` | Part A done, tagged `v1`; Part B pending (sent only after they receive the `v1` tag) |

### Running Task 1 (answer engine)

```bash
cd task1-rag
pip install -r requirements.txt
cp .env.example .env                      # add OPENAI_API_KEY
python ingest.py --corpus ../corpus       # build the index
python app.py                             # http://127.0.0.1:8000  (POST /ask, GET /health)
python eval/run.py --direct               # 40-question eval -> eval/results.md
python -m pytest                          # offline tests
```

### Running Task 2 (Billing Helper agent)

```bash
python sandbox/server.py                  # terminal 1: the billing sandbox on :8787

cd task2-agent                            # terminal 2
pip install -r requirements.txt
cp .env.example .env                      # add OPENAI_API_KEY
python chat.py chat --email maya.chen@lumenbooks.example --trace
python -m pytest                          # 77 tests, no API key needed
```

### Running Task 3 (Weekly Digest CLI)

```bash
cd task3-digest
pip install -r requirements.txt
python digest.py --input ../task3_data/responses_sample.csv --week 2026-08-17 --out outputs/digest_2026-08-17.md
```

Or from the repo root, exactly as written in the brief:
```bash
python digest.py digest --input task3_data/responses_sample.csv --week 2026-08-17 --out task3-digest/outputs/digest_2026-08-17.md
```

To run the Task 3 test suite:
```bash
cd task3-digest
python -m pytest
```
