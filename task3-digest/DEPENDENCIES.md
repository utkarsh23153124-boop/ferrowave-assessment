# DEPENDENCIES.md

Task: Task 3 (Weekly Insights Digest)

Every third-party package you added beyond the language's standard library. We will ask
about entries at random in the live session.

| Package | Version | What it does for me here | What I would have to write if it were removed | Risk (size, maintenance, licence, lock-in) |
|---|---|---|---|---|
| `openai` | `3.7.0` | Official client library for calling `gpt-4o-mini` with structured JSON output and token accounting. | Raw HTTP client calls using standard library `urllib.request` or `http.client`, manual retry logic, and JSON parsing. | Low risk; MIT licensed; vendor lock-in to OpenAI API format (mitigated by isolated `themes.py` interface). |
| `python-dateutil` | `2.9.0` | Robust fallback parser for unconventional datetime formats without crashing. | Custom regex cascades for obscure date format variations or expanding `strptime` format candidate lists. | Very low risk; dual Apache 2.0 / BSD license; standard industry utility with minimal footprint. |
| `pytest` | `9.1.1` | Test discovery and test runner for our 26 tests covering parser edge cases, injection defense, NPS math, watch-out rules, and end-to-end CLI runs. | Custom test runner using Python standard library `unittest`. | Development dependency only; zero production runtime footprint. |

## Framework accounting (Task 2)

*(N/A for Task 3 — no agent framework utilized).*
