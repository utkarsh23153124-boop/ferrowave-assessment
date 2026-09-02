"""
Data parsing, cleaning, and normalization module for survey responses.
Handles real-world messy CSV data, multiple date formats, malformed scores,
spam rows, deduplication, and prompt injection attempts.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateutil import parser as date_parser


INJECTION_PATTERNS = [
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard previous instructions",
    "you are now",
    "system prompt",
    "approved by management",
    "report the nps as",
]

SPAM_DOMAINS = [
    "best-seo-tools.example",
    "backlinks",
]

NOISE_COMMENTS = {
    "-",
    "n/a",
    "na",
    "no comment",
    "none",
    "good",
    "fine",
    "ok",
    "okay",
    "",
}

WORD_TO_SCORE = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_date(raw_date: str) -> Optional[datetime]:
    """
    Parses timestamps supporting ISO 8601, US (MM/DD/YYYY), and EU (DD-MM-YYYY) formats.
    Always returns a timezone-aware UTC datetime.
    """
    if not raw_date or not raw_date.strip():
        return None

    cleaned = raw_date.strip()

    # Explicit format matching for predictable behavior
    explicit_formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%m/%d/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ]
    for fmt in explicit_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue

    # Fallback to dateutil parser if explicit formats fail
    try:
        dt = date_parser.parse(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def parse_score(raw_score: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Parses and validates scores into integers [0, 10].
    Returns (score, rejection_reason).
    """
    if raw_score is None:
        return None, "missing_score"

    cleaned = str(raw_score).strip().lower()
    if not cleaned:
        return None, "missing_score"

    # 1. Plain integer
    try:
        val = int(cleaned)
        if 0 <= val <= 10:
            return val, None
        return None, f"score_out_of_range ({val})"
    except ValueError:
        pass

    # 2. Word representation ("ten", "eight", etc.)
    if cleaned in WORD_TO_SCORE:
        return WORD_TO_SCORE[cleaned], None

    # 3. Fraction format: "10/10", "8/10"
    fraction_match = re.match(r"^(\d+)\s*/\s*10$", cleaned)
    if fraction_match:
        val = int(fraction_match.group(1))
        if 0 <= val <= 10:
            return val, None
        return None, f"score_out_of_range ({val})"

    # 4. Phrase format: "8 out of 10"
    phrase_match = re.match(r"^(\d+)\s*out\s*of\s*10$", cleaned)
    if phrase_match:
        val = int(phrase_match.group(1))
        if 0 <= val <= 10:
            return val, None
        return None, f"score_out_of_range ({val})"

    # 5. Non-integer numeric (e.g. 7.5) -> standard NPS scores are strictly integers 0-10
    try:
        float_val = float(cleaned)
        return None, f"non_integer_score ({float_val})"
    except ValueError:
        pass

    # 6. Any other unparseable text
    return None, f"unparseable_score ('{raw_score.strip()}')"


def normalize_segment(raw_segment: str) -> str:
    """Normalizes segment names to Title Case, stripping whitespace."""
    if not raw_segment or not raw_segment.strip():
        return "Unknown"
    return raw_segment.strip().title()


def is_prompt_injection(comment: str) -> bool:
    """Detects adversarial instruction injections embedded in survey comments."""
    if not comment:
        return False
    lowered = comment.lower()
    return any(pat in lowered for pat in INJECTION_PATTERNS)


def is_spam(row: Dict[str, Any]) -> bool:
    """Identifies SEO / spam responses based on content and metadata."""
    comment = (row.get("comment") or "").lower()
    segment = normalize_segment(row.get("segment", ""))
    has_spam_domain = any(domain in comment for domain in SPAM_DOMAINS)
    has_url = bool(re.search(r"https?://|\.example\b", comment))
    is_unknown_segment = segment == "Unknown"
    return has_spam_domain or (has_url and is_unknown_segment)


def is_meaningful_comment(comment: str) -> bool:
    """Filters out noise/placeholder comments for LLM processing."""
    if not comment:
        return False
    cleaned = comment.strip().lower()
    if cleaned in NOISE_COMMENTS:
        return False
    if len(cleaned) < 3:
        return False
    return True


def clean_repeated_sentences(text: str) -> str:
    """
    Cleans up comments with artificially repeated sentences (e.g., duplicate pastes).
    """
    if not text:
        return text
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= 1:
        return text

    seen = []
    for s in sentences:
        if s not in seen:
            seen.append(s)
    return " ".join(seen)


def load_and_parse_csv(filepath: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Reads and validates a survey responses CSV file.
    Returns (valid_rows, excluded_rows).
    Never crashes on malformed CSV rows.
    """
    valid_rows: List[Dict[str, Any]] = []
    excluded_rows: List[Dict[str, Any]] = []
    seen_keys = set()

    with open(filepath, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for line_num, raw_row in enumerate(reader, start=2):
            response_id = (raw_row.get("response_id") or f"row_{line_num}").strip()
            raw_submitted_at = raw_row.get("submitted_at") or ""
            raw_score = raw_row.get("score")
            raw_comment = raw_row.get("comment") or ""
            survey = (raw_row.get("survey") or "").strip()
            segment = normalize_segment(raw_row.get("segment") or "")
            language = (raw_row.get("language") or "en").strip()
            channel = (raw_row.get("channel") or "link").strip()

            # Deduplication key: (response_id, raw_submitted_at)
            dedup_key = (response_id, raw_submitted_at.strip())
            if dedup_key in seen_keys:
                excluded_rows.append({
                    "response_id": response_id,
                    "reason": "duplicate_response_id",
                    "raw_row": raw_row,
                })
                continue
            seen_keys.add(dedup_key)

            # Date parsing
            dt = parse_date(raw_submitted_at)
            if not dt:
                excluded_rows.append({
                    "response_id": response_id,
                    "reason": f"unparseable_date ('{raw_submitted_at.strip()}')",
                    "raw_row": raw_row,
                })
                continue

            # Check prompt injection
            if is_prompt_injection(raw_comment):
                excluded_rows.append({
                    "response_id": response_id,
                    "reason": "prompt_injection_attempt",
                    "raw_row": raw_row,
                })
                continue

            # Check spam
            if is_spam(raw_row):
                excluded_rows.append({
                    "response_id": response_id,
                    "reason": "spam_detected",
                    "raw_row": raw_row,
                })
                continue

            # Parse score
            score, rejection_reason = parse_score(raw_score)
            if rejection_reason is not None:
                excluded_rows.append({
                    "response_id": response_id,
                    "reason": rejection_reason,
                    "raw_row": raw_row,
                })
                continue

            # Survey classification
            is_nps_survey = "nps" in survey.lower()
            is_csat_survey = "csat" in survey.lower()

            cleaned_comment = clean_repeated_sentences(raw_comment.strip())

            valid_rows.append({
                "response_id": response_id,
                "submitted_at": dt,
                "survey": survey,
                "is_nps_survey": is_nps_survey,
                "is_csat_survey": is_csat_survey,
                "score": score,
                "raw_comment": raw_comment,
                "comment": cleaned_comment,
                "has_meaningful_comment": is_meaningful_comment(cleaned_comment),
                "segment": segment,
                "language": language,
                "channel": channel,
            })

    return valid_rows, excluded_rows
