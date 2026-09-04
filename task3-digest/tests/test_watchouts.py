"""
Unit tests for data-driven watch-out generation.
Every watch-out must be traceable to a number that crossed a threshold.
"""

from watchouts import generate_watchouts


def _nps(nps, detractor_pct, detractors, total):
    return {
        "nps": nps,
        "detractor_pct": detractor_pct,
        "detractors": detractors,
        "total_responses": total,
    }


def _comparison(tw, pw, delta):
    return {"this_week_metrics": tw, "prev_week_metrics": pw, "delta": delta}


def test_quiet_week_produces_single_steady_line():
    comp = _comparison(_nps(20, 20.0, 2, 10), _nps(18, 22.0, 2, 9), 2)
    out = generate_watchouts([], [], comp)
    assert len(out) == 1
    assert "No threshold was crossed" in out[0]


def test_nps_move_and_detractor_share_are_reported_with_numbers():
    comp = _comparison(_nps(-8, 40.3, 25, 62), _nps(-38, 56.2, 36, 64), 30)
    out = generate_watchouts([], [], comp)
    joined = "\n".join(out)
    assert "moved up 30 points" in joined
    assert "-38 to -8" in joined
    assert "40.3%" in joined and "25 of 62" in joined


def test_rising_problem_theme_only_not_praise():
    comp = _comparison(_nps(0, 0.0, 0, 10), _nps(0, 0.0, 0, 10), 0)
    comments = [{"segment": "Growth", "language": "en"} for _ in range(6)]
    labels = ["pricing_concerns"] * 3 + ["onboarding_positive"] * 3
    prev_labels = ["pricing_concerns"]  # pricing went 1 -> 3, onboarding 0 -> 3
    out = generate_watchouts([], [], comp, comments, labels, prev_labels)
    joined = "\n".join(out)
    assert "Rising theme: Pricing" in joined
    assert "Onboarding" not in joined


def test_cross_segment_requires_three_segments():
    comp = _comparison(_nps(0, 0.0, 0, 10), _nps(0, 0.0, 0, 10), 0)
    two_segments = [{"segment": s, "language": "en"} for s in ["Growth", "Scale", "Growth"]]
    labels = ["dashboard_performance"] * 3
    out = generate_watchouts([], [], comp, two_segments, labels, labels)
    assert not any("Cross-segment" in w for w in out)

    three_segments = [{"segment": s, "language": "en"} for s in ["Growth", "Scale", "Enterprise"]]
    out = generate_watchouts([], [], comp, three_segments, labels, labels)
    assert any("Cross-segment issue: Dashboard" in w and "3 segments" in w for w in out)


def test_segment_detractor_share_needs_minimum_sample():
    comp = _comparison(_nps(0, 0.0, 0, 10), _nps(0, 0.0, 0, 10), 0)
    small = [{"segment": "Starter", "is_nps_survey": True, "score": 2} for _ in range(4)]
    assert not any("segment detractors" in w for w in generate_watchouts(small, [], comp))

    enough = [{"segment": "Starter", "is_nps_survey": True, "score": 2} for _ in range(5)]
    out = generate_watchouts(enough, [], comp)
    assert any("Starter segment detractors" in w and "5 of 5" in w for w in out)


def test_data_quality_flag_uses_exclusion_share():
    comp = _comparison(_nps(0, 0.0, 0, 10), _nps(0, 0.0, 0, 10), 0)
    dq = {"total_read": 100, "total_excluded": 15, "exclusion_reasons": {"spam_detected": 15}}
    out = generate_watchouts([], [], comp, data_quality=dq)
    assert any("15 of 100" in w and "spam_detected 15" in w for w in out)

    dq_low = {"total_read": 100, "total_excluded": 3, "exclusion_reasons": {"spam_detected": 3}}
    assert not any("Data quality" in w for w in generate_watchouts([], [], comp, data_quality=dq_low))
