"""Shared text helpers: tokenising for BM25 and overlap, normalising for quote checks."""
from __future__ import annotations

import re
from typing import List

_WORD = re.compile(r"[a-z0-9]+")
_STRIP = re.compile(r"[*`#_>|]")
_WS = re.compile(r"\s+")
INJECTION_BLOCK = re.compile(r"\[\[.*?\]\]", re.S)

# Formats whose raw bytes are prose: quotes must appear in the file itself.
PROSE_SUFFIXES = {".md", ".txt"}


def tokenize(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def normalize(text: str) -> str:
    """Collapse whitespace and strip markdown emphasis so quote checks tolerate formatting."""
    return _WS.sub(" ", _STRIP.sub("", text)).strip().lower()
