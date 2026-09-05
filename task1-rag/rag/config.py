"""Paths, model names, prices. Everything tunable lives here."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # task1-rag/
REPO_ROOT = ROOT.parent
DEFAULT_CORPUS = REPO_ROOT / "corpus"
INDEX_DIR = ROOT / "index"
MANIFEST_NAME = "_manifest.csv"

CHAT_MODEL = os.getenv("RAG_CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "text-embedding-3-small")

# USD per 1M tokens (input, output). Source: OpenAI pricing page, checked 2026-09-04.
PRICES_PER_M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "text-embedding-3-small": (0.02, 0.0),
}

TOP_K = 8            # chunks handed to the model
RETRIEVE_K = 14      # candidates pulled from each retriever before fusion
CHUNK_SIZE = 900     # characters
CHUNK_OVERLAP = 120
MAX_QUOTE_CHARS = 300


def load_env() -> None:
    """Load OPENAI_API_KEY etc. from task1-rag/.env or repo-root .env without overriding the shell."""
    for candidate in (ROOT / ".env", REPO_ROOT / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def price_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICES_PER_M.get(model, (0.0, 0.0))
    return (tokens_in * pin + tokens_out * pout) / 1_000_000
