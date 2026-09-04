"""
Digest rendering and formatting module.
Outputs clean, professional Markdown (default) and responsive HTML.
"""

from __future__ import annotations

import html as _html
from typing import Any, Dict, List


def md_inline_to_html(text: str) -> str:
    """Escapes HTML and converts **bold** spans, which watch-outs use, to <strong>."""
    escaped = _html.escape(text, quote=False)
    # Split on the bold marker; odd-indexed pieces sit between a pair of markers.
    parts = escaped.split("**")
    if len(parts) % 2 == 0:  # unbalanced markers, leave the text alone
        return escaped
    return "".join(f"<strong>{part}</strong>" if i % 2 else part for i, part in enumerate(parts))


def format_nps_val(val: Any) -> str:
    """Formats an NPS number with explicit +/- sign."""
    if val is None:
        return "N/A"
    try:
        num = int(val)
        return f"+{num}" if num > 0 else str(num)
    except (ValueError, TypeError):
        return str(val)


def render_markdown(data: Dict[str, Any]) -> str:
    """Renders the weekly digest in clean GitHub-flavored Markdown."""
    week_str = data["week_start"]
    nps_comp = data["nps_comparison"]
    tw_m = nps_comp.get("this_week_metrics")
    pw_m = nps_comp.get("prev_week_metrics")
    delta = nps_comp.get("delta")

    tw_nps_str = format_nps_val(tw_m.get("nps") if tw_m else None)
    pw_nps_str = format_nps_val(pw_m.get("nps") if pw_m else None)
    delta_str = format_nps_val(delta) if delta is not None else "N/A"
    delta_arrow = "▲" if (delta or 0) > 0 else ("▼" if (delta or 0) < 0 else "—")

    themes = data["themes"]
    watchouts = data["watchouts"]
    dq = data["data_quality"]
    diagnostics = data.get("diagnostics", {})

    lines = [
        f"# Ferrowave Pulse — Weekly Insights Digest",
        f"**Week of {week_str} (Monday to Sunday)**  ",
        f"*Generated from survey export: `{data['input_file']}`*",
        "",
        "---",
        "",
        "## 1. Headline NPS",
        "",
        "| Metric | This Week | Previous Week | Change |",
        "| :--- | :---: | :---: | :---: |",
        f"| **NPS Score** | **{tw_nps_str}** | **{pw_nps_str}** | **{delta_str} {delta_arrow}** |",
        f"| Promoters (9–10) | {tw_m['promoter_pct']}% ({tw_m['promoters']}) | {pw_m['promoter_pct'] if pw_m else 'N/A'}% ({pw_m['promoters'] if pw_m else 0}) | — |" if tw_m else "| Promoters | N/A | N/A | — |",
        f"| Passives (7–8) | {tw_m['passive_pct']}% ({tw_m['passives']}) | {pw_m['passive_pct'] if pw_m else 'N/A'}% ({pw_m['passives'] if pw_m else 0}) | — |" if tw_m else "| Passives | N/A | N/A | — |",
        f"| Detractors (0–6) | {tw_m['detractor_pct']}% ({tw_m['detractors']}) | {pw_m['detractor_pct'] if pw_m else 'N/A'}% ({pw_m['detractors'] if pw_m else 0}) | — |" if tw_m else "| Detractors | N/A | N/A | — |",
        f"| Responses Analyzed | {tw_m['total_responses']} | {pw_m['total_responses'] if pw_m else 0} | — |" if tw_m else "| Responses Analyzed | 0 | 0 | — |",
        "",
        "> [!NOTE]",
        "> NPS is computed deterministically in code: `% Promoters (9–10) − % Detractors (0–6)`. ",
        "> Calculated exclusively from relationship and onboarding NPS surveys. Post-support CSAT responses are excluded from the headline NPS index to preserve relationship-metric fidelity.",
        "",
        "---",
        "",
        "## 2. Top Common Themes in Feedback",
        "",
    ]

    for i, t in enumerate(themes, start=1):
        lines.append(f"### {i}. {t['title']} ({t['count']} mentions)")
        for quote in t.get("quotes", []):
            lines.append(f"> \"{quote}\"")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. Watch-Outs",
        "",
    ])

    for w in watchouts:
        lines.append(f"- {w}")
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 4. Data Quality & Audit Footer",
        "",
        "| Metric | Count | Description |",
        "| :--- | :---: | :--- |",
        f"| Total Rows Read | {dq['total_read']} | Raw lines ingested from survey export |",
        f"| Valid Clean Rows | {dq['total_valid']} | Rows passing date, schema, and range validation |",
        f"| Rows Used (This Week NPS) | {dq['used_this_week_nps']} | NPS surveys within target week |",
        f"| Rows Used (Prev Week NPS) | {dq['used_prev_week_nps']} | NPS surveys in comparison baseline week |",
        f"| Rows Excluded from Dataset | {dq['total_excluded']} | Malformed, duplicate, spam, or invalid rows |",
        "",
        "### Exclusion Breakdown",
        "",
    ])

    for reason, count in sorted(dq.get("exclusion_reasons", {}).items()):
        lines.append(f"- **{reason}**: {count} row(s)")

    if diagnostics:
        lines.extend([
            "",
            "### Pipeline Diagnostics",
            f"- **Theme Analysis Engine**: {diagnostics.get('model', 'offline')}",
            f"- **Tokens Consumed**: {diagnostics.get('tokens_in', 0)} prompt + {diagnostics.get('tokens_out', 0)} completion",
            f"- **Model Spend**: ${diagnostics.get('estimated_cost_usd', 0.0):.6f} USD (budget ceiling: $1.00)",
        ])

    return "\n".join(lines)


def render_html(data: Dict[str, Any]) -> str:
    """Renders the weekly digest in responsive HTML format."""
    week_str = data["week_start"]
    nps_comp = data["nps_comparison"]
    tw_m = nps_comp.get("this_week_metrics")
    pw_m = nps_comp.get("prev_week_metrics")
    delta = nps_comp.get("delta")

    tw_nps_str = format_nps_val(tw_m.get("nps") if tw_m else None)
    pw_nps_str = format_nps_val(pw_m.get("nps") if pw_m else None)
    delta_str = format_nps_val(delta) if delta is not None else "N/A"

    themes = data["themes"]
    watchouts = data["watchouts"]
    dq = data["data_quality"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Weekly Insights Digest — Week of {week_str}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1e293b; background: #f8fafc; }}
    .card {{ background: white; border-radius: 12px; padding: 28px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); margin-bottom: 24px; border: 1px solid #e2e8f0; }}
    h1 {{ color: #0f172a; margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    th {{ background: #f1f5f9; font-weight: 600; }}
    blockquote {{ border-left: 4px solid #3b82f6; margin: 8px 0; padding: 8px 16px; background: #eff6ff; font-style: italic; color: #1e40af; border-radius: 4px; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.85em; }}
    .badge-pos {{ background: #dcfce7; color: #166534; }}
    .badge-neg {{ background: #fee2e2; color: #991b1b; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Ferrowave Pulse — Weekly Insights Digest</h1>
    <p><strong>Target Week:</strong> {week_str} &nbsp;|&nbsp; <strong>Source:</strong> <code>{data['input_file']}</code></p>
    
    <h2>1. Headline NPS</h2>
    <table>
      <thead>
        <tr><th>Metric</th><th>This Week</th><th>Previous Week</th><th>Delta</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>NPS Score</strong></td><td><strong>{tw_nps_str}</strong></td><td>{pw_nps_str}</td><td><span class="badge {'badge-pos' if (delta or 0) >= 0 else 'badge-neg'}">{delta_str}</span></td></tr>
        <tr><td>Promoters (9-10)</td><td>{tw_m['promoter_pct'] if tw_m else 'N/A'}%</td><td>{pw_m['promoter_pct'] if pw_m else 'N/A'}%</td><td>—</td></tr>
        <tr><td>Detractors (0-6)</td><td>{tw_m['detractor_pct'] if tw_m else 'N/A'}%</td><td>{pw_m['detractor_pct'] if pw_m else 'N/A'}%</td><td>—</td></tr>
      </tbody>
    </table>

    <h2>2. Top 5 Themes</h2>
    {''.join(f"<h3>{i}. {_html.escape(t['title'])} ({t['count']} mentions)</h3>" + ''.join(f"<blockquote>\"{_html.escape(q)}\"</blockquote>" for q in t.get('quotes', [])) for i, t in enumerate(themes, 1))}

    <h2>3. Watch-Outs</h2>
    <ul>
      {''.join(f"<li>{md_inline_to_html(w)}</li>" for w in watchouts)}
    </ul>

    <h2>4. Data Quality & Audit</h2>
    <p>Read {dq['total_read']} rows &bull; Valid {dq['total_valid']} &bull; Excluded {dq['total_excluded']}</p>
  </div>
</body>
</html>"""
    return html


def render_digest(data: Dict[str, Any], fmt: str = "markdown") -> str:
    """Unified entry point for rendering formatted output."""
    if fmt.lower() == "html":
        return render_html(data)
    return render_markdown(data)
