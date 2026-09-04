# Task 3: Ferrowave Pulse Weekly Insights Digest

A production-grade, time-boxed CLI tool that transforms raw, messy survey exports into an executive weekly feedback digest.

## Features

- **Robust Data Cleaning & Normalization**: Seamlessly handles multiple date formats (ISO, US, EU), irregular score types (`"ten"`, `"8 out of 10"`, `"10/10"`, blank), segment casing (`GROWTH` -> `Growth`), and deduplication.
- **Prompt Injection Defense**: Pre-LLM detection and exclusion of adversarial prompt injection attempts (specifically row `r_1345`).
- **Deterministic NPS Mathematics**: All NPS calculations (promoters %, detractors %, passives %, delta) are executed 100% in Python code with zero model involvement.
- **Auditable Theme Extraction**: Two-stage pipeline where `gpt-4o-mini` classifies individual comments in a single batch, and Python code tallies exact mention counts and selects representative quotes.
- **Offline Fallback Engine**: Fully functional offline rule-based clustering if no OpenAI API key is supplied.
- **Data-Driven Watch-Outs**: Each watch-out is emitted only when a computed number crosses a threshold (NPS movement, detractor share, rising or cross-segment problem themes, worst segment, non-English share, exclusion rate) and carries those numbers in the sentence. Thresholds live at the top of `watchouts.py`.
- **Week Handling**: `--week` is the Monday of the target week. Any other weekday is snapped back to its Monday with a note on stderr; a week with no rows renders `N/A` rather than failing.
- **Multi-Format Rendering**: Generates clean GitHub-flavored Markdown (default) and responsive HTML.
- **Data Quality & Audit Footer**: Comprehensive tracking of every row read, used, and excluded, with exact reason breakdowns.

## Quick Start (One Command)

From this directory (`task3-digest/`):

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set OpenAI API Key (optional, defaults to offline engine if unset)
export OPENAI_API_KEY="sk-..."  # On Windows PowerShell: $env:OPENAI_API_KEY="sk-..."

# 3. Generate Weekly Digest (Markdown)
python digest.py --input ../task3_data/responses_sample.csv --week 2026-08-17 --out outputs/digest_2026-08-17.md

# Also supports exact brief syntax:
python digest.py digest --input ../task3_data/responses_sample.csv --week 2026-08-17 --out outputs/digest_2026-08-17.md
```

To generate HTML:
```bash
python digest.py --input ../task3_data/responses_sample.csv --week 2026-08-17 --out outputs/digest_2026-08-17.html --format html
```

## Running Tests

Unit tests for parsing, scoring, injection detection, NPS math and watch-out rules, plus end-to-end runs on the real sample file in both formats:

```bash
python -m pytest
```

## Architecture

```
task3-digest/
├── digest.py         # CLI orchestration & entry point
├── parser.py         # CSV ingestion, data validation & prompt injection defense
├── nps.py            # Deterministic NPS calculation & time window arithmetic
├── themes.py         # LLM batch classification & programmatic counting
├── watchouts.py      # Threshold-based watch-outs computed from NPS, theme labels, segments
├── formatter.py      # Markdown and HTML template renderers
├── pii.py            # Phone, email, and card number redaction
├── tests/            # Unit + end-to-end tests
├── outputs/          # Generated digest artifacts
├── requirements.txt  # Minimal dependencies
├── DECISIONS.md      # Architectural and data decisions
├── ITERATIONS.md     # Development & debugging log
├── DEPENDENCIES.md   # Third-party library accounting
└── AI_USAGE.md       # AI assistance & manual verification accounting
```
