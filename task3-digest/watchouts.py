"""
Watch-out detection for the weekly digest.

Every watch-out is derived from numbers computed in code: the NPS comparison,
the per-comment theme labels (from themes.py), segment and language breakdowns,
and the data-quality audit. No sentence is emitted unless the data behind it
crossed a threshold, and every sentence carries the numbers it was built from.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from themes import PROBLEM_THEMES, STANDARD_THEMES

# Thresholds. Kept in one place so they can be tuned or exposed as CLI flags later.
NPS_MOVE_POINTS = 10          # |delta| at or above this is called out
DETRACTOR_SHARE_PCT = 35.0    # detractor share at or above this is called out
THEME_MIN_MENTIONS = 3        # a theme needs this many mentions to be a watch-out
THEME_RISE_MIN_DELTA = 2      # and must have grown by at least this many vs last week
THEME_SEGMENT_SPREAD = 3      # problem theme seen in this many segments = platform-wide
SEGMENT_MIN_RESPONSES = 5     # segment needs this many NPS responses to be judged
SEGMENT_DETRACTOR_PCT = 50.0  # segment detractor share at or above this is called out
NON_ENGLISH_SHARE_PCT = 15.0  # share of comments not in English worth flagging
EXCLUDED_SHARE_PCT = 10.0     # share of raw rows excluded worth flagging
MAX_RISING_THEMES = 2         # cap so theme trends do not crowd out other signals
MAX_SPREAD_THEMES = 2
MAX_WATCHOUTS = 8


def _pct(part: int, whole: int) -> float:
    return round((part / whole) * 100.0, 1) if whole else 0.0


def _title(theme_id: str, theme_titles: Optional[Dict[str, str]]) -> str:
    if theme_titles and theme_id in theme_titles:
        return theme_titles[theme_id]
    return STANDARD_THEMES.get(theme_id, theme_id.replace("_", " ").title())


def generate_watchouts(
    this_week_rows: List[Dict[str, Any]],
    prev_week_rows: List[Dict[str, Any]],
    nps_comparison: Dict[str, Any],
    this_week_comments: Optional[List[Dict[str, Any]]] = None,
    this_week_labels: Optional[List[str]] = None,
    prev_week_labels: Optional[List[str]] = None,
    theme_titles: Optional[Dict[str, str]] = None,
    data_quality: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Builds an ordered list of watch-out sentences for the target week.

    this_week_comments / this_week_labels are aligned lists: label i belongs to comment i.
    prev_week_labels are the labels for last week's comments (order irrelevant).
    """
    this_week_comments = this_week_comments or []
    this_week_labels = this_week_labels or []
    prev_week_labels = prev_week_labels or []
    watchouts: List[str] = []

    tw_m = nps_comparison.get("this_week_metrics")
    pw_m = nps_comparison.get("prev_week_metrics")
    delta = nps_comparison.get("delta")

    # 1. Headline NPS movement
    if tw_m and pw_m and delta is not None and abs(delta) >= NPS_MOVE_POINTS:
        direction = "up" if delta > 0 else "down"
        watchouts.append(
            f"**NPS moved {direction} {abs(delta)} points** ({pw_m['nps']:+d} to {tw_m['nps']:+d}) "
            f"on {tw_m['total_responses']} responses this week versus {pw_m['total_responses']} last week. "
            f"Weekly samples this small swing easily; treat the direction as a signal and the size as noisy."
        )

    # 2. Detractor share
    if tw_m and tw_m.get("detractor_pct", 0.0) >= DETRACTOR_SHARE_PCT:
        watchouts.append(
            f"**High detractor share**: {tw_m['detractor_pct']}% of NPS responses "
            f"({tw_m['detractors']} of {tw_m['total_responses']}) scored 0 to 6 this week."
        )

    # 3. Theme trends and spread (only when labels are available)
    tw_counts = Counter(l for l in this_week_labels if l != "other")
    pw_counts = Counter(l for l in prev_week_labels if l != "other")

    theme_segments: Dict[str, set] = defaultdict(set)
    for comment, label in zip(this_week_comments, this_week_labels):
        if label != "other":
            theme_segments[label].add(comment.get("segment", "Unknown"))

    # Rising problem themes: a growing complaint is a watch-out, growing praise is not.
    rising = 0
    for theme_id, count in tw_counts.most_common():
        if theme_id not in PROBLEM_THEMES or rising >= MAX_RISING_THEMES:
            continue
        prev = pw_counts.get(theme_id, 0)
        if count >= THEME_MIN_MENTIONS and count - prev >= THEME_RISE_MIN_DELTA:
            rising += 1
            watchouts.append(
                f"**Rising theme: {_title(theme_id, theme_titles)}** went from {prev} to {count} "
                f"mentions week over week."
            )

    spread = 0
    for theme_id in sorted(PROBLEM_THEMES, key=lambda t: -tw_counts.get(t, 0)):
        if spread >= MAX_SPREAD_THEMES:
            break
        count = tw_counts.get(theme_id, 0)
        segments = theme_segments.get(theme_id, set())
        if count >= THEME_MIN_MENTIONS and len(segments) >= THEME_SEGMENT_SPREAD:
            spread += 1
            watchouts.append(
                f"**Cross-segment issue: {_title(theme_id, theme_titles)}** had {count} mentions "
                f"spread across {len(segments)} segments ({', '.join(sorted(segments))}), "
                f"so it is not confined to one plan tier."
            )

    # 4. Segment with a detractor problem (NPS surveys only)
    seg_scores: Dict[str, List[int]] = defaultdict(list)
    for r in this_week_rows:
        if r.get("is_nps_survey") and r.get("score") is not None:
            seg_scores[r.get("segment", "Unknown")].append(r["score"])
    worst = None
    for seg, scores in seg_scores.items():
        if len(scores) < SEGMENT_MIN_RESPONSES:
            continue
        detractors = sum(1 for s in scores if s <= 6)
        share = _pct(detractors, len(scores))
        if share >= SEGMENT_DETRACTOR_PCT and (worst is None or share > worst[2]):
            worst = (seg, detractors, share, len(scores))
    if worst:
        seg, detractors, share, n = worst
        watchouts.append(
            f"**{seg} segment detractors**: {detractors} of {n} NPS responses ({share}%) were detractors, "
            f"the highest share of any segment this week."
        )

    # 5. Language coverage of the comments actually analysed
    if this_week_comments:
        langs = Counter((c.get("language") or "en").lower() for c in this_week_comments)
        non_en = sum(n for lang, n in langs.items() if lang != "en")
        share = _pct(non_en, len(this_week_comments))
        if share >= NON_ENGLISH_SHARE_PCT:
            listed = ", ".join(f"{lang} {n}" for lang, n in langs.most_common() if lang != "en")
            watchouts.append(
                f"**Non-English feedback**: {share}% of analysed comments ({non_en} of {len(this_week_comments)}) "
                f"were not in English ({listed}). Check that theme labels hold up for those languages."
            )

    # 6. Data quality
    if data_quality:
        total_read = data_quality.get("total_read", 0)
        excluded = data_quality.get("total_excluded", 0)
        share = _pct(excluded, total_read)
        if total_read and share >= EXCLUDED_SHARE_PCT:
            reasons = data_quality.get("exclusion_reasons", {})
            top = ", ".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:3])
            watchouts.append(
                f"**Data quality**: {excluded} of {total_read} rows ({share}%) were excluded ({top}). "
                f"See the audit footer before quoting any number from this digest."
            )

    if not watchouts:
        watchouts.append(
            "No threshold was crossed this week: NPS, detractor share, theme volumes, and data quality all look steady."
        )

    return watchouts[:MAX_WATCHOUTS]
