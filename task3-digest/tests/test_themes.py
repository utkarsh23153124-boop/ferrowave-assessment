"""
Unit tests for theme extraction and deterministic offline fallback.
"""

from themes import extract_themes_offline


def test_extract_themes_offline():
    comments = [
        {"comment": "The dashboard freezes when we apply date filters over a year of data."},
        {"comment": "Dashboard takes 20+ seconds to load once you have responses."},
        {"comment": "The price went up 25% at renewal with no real change."},
        {"comment": "Renewal came in higher than expected. Cost is steep."},
        {"comment": "The Zendesk trigger is brilliant. Surveys go out instantly."},
        {"comment": "Slack integration is great."},
        {"comment": "Took three days to get a reply from support."},
        {"comment": "CSV export keeps missing the most recent day of responses."},
    ]

    themes, diag = extract_themes_offline(comments, top_n=5)
    assert len(themes) > 0
    theme_ids = [t["id"] for t in themes]

    # Dashboard and pricing must be identified
    assert "dashboard_performance" in theme_ids
    assert "pricing_concerns" in theme_ids

    for t in themes:
        assert t["count"] > 0
        assert len(t["quotes"]) > 0
