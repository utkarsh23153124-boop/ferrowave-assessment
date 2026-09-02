#!/usr/bin/env python3
"""
Ferrowave Pulse — Weekly Insights Digest CLI Tool.
Reads survey exports, cleans messy real-world data, computes deterministic NPS metrics,
extracts top customer themes, identifies critical watch-outs, and renders an audited report.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict

from parser import load_and_parse_csv
from nps import (
    compute_nps_comparison,
    filter_responses_by_window,
    get_week_bounds,
)
from themes import extract_themes_llm
from watchouts import generate_watchouts
from formatter import render_digest


def run_digest(
    input_path: str,
    week_start: str,
    out_path: str,
    output_format: str = "markdown",
    include_csat_in_nps: bool = False,
    top_themes_count: int = 5,
    verbose: bool = False,
) -> None:
    """Executes the full digest generation pipeline."""
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"Ingesting raw data from '{input_path}'...")

    # Step 1: Load and clean CSV
    valid_rows, excluded_rows = load_and_parse_csv(input_path)
    total_read = len(valid_rows) + len(excluded_rows)

    if verbose:
        print(f"Read {total_read} rows: {len(valid_rows)} valid, {len(excluded_rows)} excluded.")

    # Step 2: Compute NPS Comparison (pure Python arithmetic)
    nps_comp = compute_nps_comparison(
        valid_rows,
        week_start,
        only_nps_surveys=not include_csat_in_nps,
    )

    tw_start, tw_end, pw_start, pw_end = (
        nps_comp["this_week_start"],
        nps_comp["this_week_end"],
        nps_comp["prev_week_start"],
        nps_comp["prev_week_end"],
    )

    # Step 3: Get comments for target week (CSAT comments included for thematic feedback)
    tw_all_rows = filter_responses_by_window(valid_rows, tw_start, tw_end, only_nps_surveys=False)
    pw_all_rows = filter_responses_by_window(valid_rows, pw_start, pw_end, only_nps_surveys=False)

    meaningful_comments = [r for r in tw_all_rows if r.get("has_meaningful_comment")]

    if verbose:
        print(f"Analyzing {len(meaningful_comments)} feedback comments in target week...")

    # Step 4: Extract themes (LLM with deterministic offline fallback)
    themes, diagnostics = extract_themes_llm(
        meaningful_comments,
        top_n=top_themes_count,
    )

    # Step 5: Generate rule-based watch-out signals
    watchouts = generate_watchouts(tw_all_rows, pw_all_rows, nps_comp)

    # Step 6: Assemble data quality audit
    reasons_counter: Dict[str, int] = {}
    for r in excluded_rows:
        reason_label = r["reason"].split(" (")[0]
        reasons_counter[reason_label] = reasons_counter.get(reason_label, 0) + 1

    dq_audit = {
        "total_read": total_read,
        "total_valid": len(valid_rows),
        "total_excluded": len(excluded_rows),
        "used_this_week_nps": nps_comp["this_week_count"],
        "used_prev_week_nps": nps_comp["prev_week_count"],
        "exclusion_reasons": reasons_counter,
    }

    # Step 7: Render and save digest
    render_data: Dict[str, Any] = {
        "input_file": os.path.basename(input_path),
        "week_start": week_start,
        "nps_comparison": nps_comp,
        "themes": themes,
        "watchouts": watchouts,
        "data_quality": dq_audit,
        "diagnostics": diagnostics,
    }

    rendered_output = render_digest(render_data, fmt=output_format)

    # Ensure parent output directory exists
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(rendered_output)

    print(f"Weekly digest successfully written to: {out_file.resolve()}")
    if verbose:
        print(f"Theme Engine: {diagnostics.get('model')} | Spend: ${diagnostics.get('estimated_cost_usd', 0):.6f}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds CLI argument parser supporting both direct flags and 'digest' subcommand."""
    parser = argparse.ArgumentParser(
        description="Ferrowave Pulse Weekly Insights Digest Generator"
    )

    # Allow optional subcommand 'digest' to match exact brief `<cmd> digest --input ...`
    subparsers = parser.add_subparsers(dest="subcommand", required=False)
    digest_sub = subparsers.add_parser("digest", help="Generate weekly digest")

    for p in (parser, digest_sub):
        p.add_argument(
            "--input",
            "-i",
            default="../task3_data/responses_sample.csv",
            help="Path to survey export CSV",
        )
        p.add_argument(
            "--week",
            "-w",
            default="2026-08-17",
            help="Start date of target week (YYYY-MM-DD, Monday)",
        )
        p.add_argument(
            "--out",
            "-o",
            default="outputs/digest_2026-08-17.md",
            help="Output path for rendered digest",
        )
        p.add_argument(
            "--format",
            choices=["markdown", "html"],
            default="markdown",
            help="Output format (markdown or html)",
        )
        p.add_argument(
            "--include-csat",
            action="store_true",
            help="Include Post-support CSAT responses in the headline NPS score",
        )
        p.add_argument(
            "--themes",
            type=int,
            default=5,
            help="Number of top themes to extract (default: 5)",
        )
        p.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Print diagnostic pipeline logs",
        )

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    run_digest(
        input_path=args.input,
        week_start=args.week,
        out_path=args.out,
        output_format=args.format,
        include_csat_in_nps=args.include_csat,
        top_themes_count=args.themes,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
