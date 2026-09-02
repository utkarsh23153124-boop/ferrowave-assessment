"""
NPS arithmetic and time-window calculation module.
All calculations are performed strictly in Python code with zero model involvement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def get_week_bounds(week_start_str: str) -> Tuple[datetime, datetime, datetime, datetime]:
    """
    Given a week starting date string 'YYYY-MM-DD' (assumed Monday),
    computes:
    - this_week_start: Monday 00:00:00 UTC
    - this_week_end:   Sunday 23:59:59.999999 UTC
    - prev_week_start: Previous Monday 00:00:00 UTC
    - prev_week_end:   Previous Sunday 23:59:59.999999 UTC
    """
    parsed = datetime.strptime(week_start_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # Ensure start is at 00:00:00
    this_week_start = datetime(parsed.year, parsed.month, parsed.day, 0, 0, 0, tzinfo=timezone.utc)
    this_week_end = this_week_start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

    prev_week_start = this_week_start - timedelta(days=7)
    prev_week_end = this_week_start - timedelta(microseconds=1)

    return this_week_start, this_week_end, prev_week_start, prev_week_end


def filter_responses_by_window(
    rows: List[Dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    only_nps_surveys: bool = True,
) -> List[Dict[str, Any]]:
    """
    Filters rows within [start_dt, end_dt].
    If only_nps_surveys is True, includes only rows where survey name contains 'NPS'.
    """
    filtered = []
    for r in rows:
        dt = r["submitted_at"]
        if start_dt <= dt <= end_dt:
            if only_nps_surveys and not r.get("is_nps_survey", False):
                continue
            filtered.append(r)
    return filtered


def compute_nps_metrics(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Computes Net Promoter Score and breakdown from a list of rows.
    Formula:
      Promoters: score 9 or 10
      Passives:  score 7 or 8
      Detractors: score 0 to 6
      NPS = % Promoters - % Detractors
    Returns None if no rows with valid scores are available.
    """
    valid_scores = [r["score"] for r in rows if r.get("score") is not None]
    total = len(valid_scores)
    if total == 0:
        return None

    promoters = sum(1 for s in valid_scores if s >= 9)
    passives = sum(1 for s in valid_scores if 7 <= s <= 8)
    detractors = sum(1 for s in valid_scores if s <= 6)

    promoter_pct = (promoters / total) * 100.0
    passive_pct = (passives / total) * 100.0
    detractor_pct = (detractors / total) * 100.0

    # Headline NPS is typically rounded to the nearest integer
    nps_raw = promoter_pct - detractor_pct
    nps_rounded = round(nps_raw)

    return {
        "nps": nps_rounded,
        "nps_raw": round(nps_raw, 2),
        "total_responses": total,
        "promoters": promoters,
        "promoter_pct": round(promoter_pct, 1),
        "passives": passives,
        "passive_pct": round(passive_pct, 1),
        "detractors": detractors,
        "detractor_pct": round(detractor_pct, 1),
    }


def compute_nps_comparison(
    rows: List[Dict[str, Any]],
    week_start_str: str,
    only_nps_surveys: bool = True,
) -> Dict[str, Any]:
    """
    Computes headline NPS comparison for requested week vs previous week.
    """
    tw_start, tw_end, pw_start, pw_end = get_week_bounds(week_start_str)

    tw_rows = filter_responses_by_window(rows, tw_start, tw_end, only_nps_surveys=only_nps_surveys)
    pw_rows = filter_responses_by_window(rows, pw_start, pw_end, only_nps_surveys=only_nps_surveys)

    tw_metrics = compute_nps_metrics(tw_rows)
    pw_metrics = compute_nps_metrics(pw_rows)

    delta: Optional[int] = None
    delta_raw: Optional[float] = None
    if tw_metrics is not None and pw_metrics is not None:
        delta = tw_metrics["nps"] - pw_metrics["nps"]
        delta_raw = round(tw_metrics["nps_raw"] - pw_metrics["nps_raw"], 2)

    return {
        "week_start": week_start_str,
        "this_week_start": tw_start,
        "this_week_end": tw_end,
        "prev_week_start": pw_start,
        "prev_week_end": pw_end,
        "this_week_metrics": tw_metrics,
        "prev_week_metrics": pw_metrics,
        "this_week_count": len(tw_rows),
        "prev_week_count": len(pw_rows),
        "delta": delta,
        "delta_raw": delta_raw,
    }
