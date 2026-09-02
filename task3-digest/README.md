# Task 3: Ferrowave Pulse Weekly Insights Digest

A production-grade, time-boxed CLI tool that transforms raw, messy survey exports into an executive weekly feedback digest.

## Features

- **Robust Data Cleaning & Normalization**: Seamlessly handles multiple date formats (ISO, US, EU), irregular score types (`"ten"`, `"8 out of 10"`, `"10/10"`, blank), segment casing (`GROWTH` -> `Growth`), and deduplication.
- **Prompt Injection Defense**: Pre-LLM detection and exclusion of adversarial prompt injection attempts (specifically row `r_1345`).
- **Deterministic NPS Mathematics**: All NPS calculations (promoters %, detractors %, passives %, delta) are executed 100% in Python code with zero model involvement.
- **Auditable Theme Extraction**: Two-stage pipeline where `gpt-4o-mini` classifies individual comments in a single batch, and Python code tallies exact mention counts and selects representative quotes.
- **Offline Fallback Engine**: Fully functional offline rule-based clustering if no OpenAI API key is supplied.
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

Comprehensive test suite covering date parsing, score conversions, injection detection, and NPS math:

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
├── watchouts.py      # Rule-based cross-segment friction & anomaly detection
├── formatter.py      # Markdown and HTML template renderers
├── pii.py            # Phone, email, and card number redaction
├── tests/            # 16 unit tests for all edge cases
├── outputs/          # Generated digest artifacts
├── requirements.txt  # Minimal dependencies
├── DECISIONS.md      # Architectural and data decisions
├── ITERATIONS.md     # Development & debugging log
├── DEPENDENCIES.md   # Third-party library accounting
└── AI_USAGE.md       # AI assistance & manual verification accounting
```
