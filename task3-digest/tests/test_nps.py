"""
Unit tests for pure Python NPS computation.
"""

from nps import compute_nps_metrics, get_week_bounds


def test_nps_perfect_score():
    # 10 promoters, 0 detractors -> 100
    rows = [{"score": 10} for _ in range(10)]
    metrics = compute_nps_metrics(rows)
    assert metrics is not None
    assert metrics["nps"] == 100
    assert metrics["promoter_pct"] == 100.0
    assert metrics["detractor_pct"] == 0.0


def test_nps_balanced():
    # 5 promoters (10), 3 passives (8), 2 detractors (4)
    # Promoters = 50%, Detractors = 20% -> NPS = +30
    rows = (
        [{"score": 10} for _ in range(5)]
        + [{"score": 8} for _ in range(3)]
        + [{"score": 4} for _ in range(2)]
    )
    metrics = compute_nps_metrics(rows)
    assert metrics is not None
    assert metrics["nps"] == 30
    assert metrics["promoters"] == 5
    assert metrics["passives"] == 3
    assert metrics["detractors"] == 2
    assert metrics["total_responses"] == 10


def test_nps_empty():
    assert compute_nps_metrics([]) is None


def test_week_bounds():
    tw_s, tw_e, pw_s, pw_e = get_week_bounds("2026-08-17")
    assert tw_s.year == 2026 and tw_s.month == 8 and tw_s.day == 17
    assert tw_e.year == 2026 and tw_e.month == 8 and tw_e.day == 23
    assert pw_s.year == 2026 and pw_s.month == 8 and pw_s.day == 10
    assert pw_e.year == 2026 and pw_e.month == 8 and pw_e.day == 16
