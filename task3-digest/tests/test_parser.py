"""
Unit tests for data parsing, date formats, score conversions, and edge cases.
"""

from datetime import datetime, timezone
import pytest
from parser import parse_date, parse_score, normalize_segment, is_spam, is_prompt_injection


def test_parse_date_iso():
    dt = parse_date("2026-08-17T09:34:02Z")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 8 and dt.day == 17
    assert dt.tzinfo == timezone.utc


def test_parse_date_us_format():
    dt = parse_date("08/11/2026 12:25")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 8 and dt.day == 11
    assert dt.hour == 12 and dt.minute == 25


def test_parse_date_eu_format():
    dt = parse_date("20-08-2026 23:01")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 8 and dt.day == 20
    assert dt.hour == 23 and dt.minute == 1


def test_parse_score_integers():
    assert parse_score("10") == (10, None)
    assert parse_score("0") == (0, None)
    assert parse_score(" 9 ") == (9, None)


def test_parse_score_words():
    assert parse_score("ten") == (10, None)
    assert parse_score("eight") == (8, None)
    assert parse_score("zero") == (0, None)


def test_parse_score_fractions_and_phrases():
    assert parse_score("10/10") == (10, None)
    assert parse_score("8 out of 10") == (8, None)


def test_parse_score_invalid():
    score, reason = parse_score("")
    assert score is None and reason == "missing_score"

    score, reason = parse_score("N/A")
    assert score is None and "unparseable_score" in reason

    score, reason = parse_score("-1")
    assert score is None and "score_out_of_range" in reason

    score, reason = parse_score("7.5")
    assert score is None and "non_integer_score" in reason


def test_normalize_segment():
    assert normalize_segment("growth") == "Growth"
    assert normalize_segment("GROWTH") == "Growth"
    assert normalize_segment("Starter ") == "Starter"
    assert normalize_segment("STARTER") == "Starter"
    assert normalize_segment("") == "Unknown"


def test_spam_detection():
    spam_row = {
        "comment": "Amazing!!! Get 500 free backlinks at best-seo-tools.example",
        "segment": "unknown",
    }
    assert is_spam(spam_row) is True

    valid_row = {
        "comment": "Dashboard is slow to load",
        "segment": "Scale",
    }
    assert is_spam(valid_row) is False
