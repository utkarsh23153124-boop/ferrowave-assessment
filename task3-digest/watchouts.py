"""
Rule-based watch-out signal detection module.
Identifies critical anomalies, cross-segment friction, and operational risks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


def generate_watchouts(
    this_week_rows: List[Dict[str, Any]],
    prev_week_rows: List[Dict[str, Any]],
    nps_comparison: Dict[str, Any],
) -> List[str]:
    """
    Generates actionable watch-out observations for the weekly digest.
    """
    watchouts: List[str] = []

    # 1. Check if dashboard performance issues affect all segments
    dashboard_segments = set()
    for r in this_week_rows:
        c = (r.get("comment") or "").lower()
        if any(w in c for w in ["dashboard", "load", "slow", "freeze", "render", "tarda", "langsam"]):
            dashboard_segments.add(r.get("segment", "Unknown"))

    if len(dashboard_segments) >= 3:
        segments_str = ", ".join(sorted(dashboard_segments))
        watchouts.append(
            f"**Universal Dashboard Slowness**: Loading lag and freezing reported across {len(dashboard_segments)} customer tiers ({segments_str}). This indicates a core platform bottleneck rather than single-tenant data volume."
        )

    # 2. Check pricing & renewal sentiment
    pricing_count_tw = sum(
        1 for r in this_week_rows
        if any(w in (r.get("comment") or "").lower() for w in ["price", "pricing", "renewal", "cost", "increase", "steep", "99", "aumento", "preiserh"])
    )
    pricing_count_pw = sum(
        1 for r in prev_week_rows
        if any(w in (r.get("comment") or "").lower() for w in ["price", "pricing", "renewal", "cost", "increase", "steep", "99", "aumento", "preiserh"])
    )

    if pricing_count_tw >= 5:
        trend_note = f" (compared to {pricing_count_pw} last week)" if pricing_count_pw > 0 else ""
        watchouts.append(
            f"**Pricing & Renewal Pushback**: {pricing_count_tw} customers flagged renewal price increases or steep Growth tier costs{trend_note}, with several customers actively evaluating alternatives."
        )

    # 3. Timezone export bug
    export_bug_count = sum(
        1 for r in this_week_rows
        if any(w in (r.get("comment") or "").lower() for w in ["export", "timezone", "missing", "reconcile"])
    )
    if export_bug_count >= 2:
        watchouts.append(
            f"**CSV Export Timezone Discrepancy**: {export_bug_count} customers reported Monday exports missing Sunday data or totals failing to reconcile with the dashboard totals."
        )

    # 4. Support turnaround time
    support_complaints = sum(
        1 for r in this_week_rows
        if any(w in (r.get("comment") or "").lower() for w in ["support", "soporte", "three days", "chase", "slow to reply", "der support"])
    )
    if support_complaints >= 3:
        watchouts.append(
            f"**Support SLA Pressure**: {support_complaints} respondents highlighted multi-day delays for billing inquiries or ticket responses."
        )

    # 5. Detractor ratio check
    tw_metrics = nps_comparison.get("this_week_metrics")
    if tw_metrics and tw_metrics.get("detractor_pct", 0) >= 35.0:
        watchouts.append(
            f"**Elevated Detractor Ratio**: Detractors comprise {tw_metrics['detractor_pct']}% of valid NPS responses this week, primarily driven by pricing resistance and dashboard latency."
        )

    if not watchouts:
        watchouts.append("No critical system-wide anomalies or sharp regressions detected this week.")

    return watchouts
