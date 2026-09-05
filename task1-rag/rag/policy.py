"""Precedence and visibility rules. These are enforced in code, not in the prompt.

Order of authority follows the Terms of Service s.14.1 (Order Form > Terms > Policies >
Documentation) extended downwards to the kinds of content the corpus actually contains.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, Tuple

# Lower tier number = higher authority.
TIER_BY_FOLDER: Dict[str, int] = {
    "legal": 1,
    "policies": 1,
    "pricing": 1,
    "product-docs": 2,
    "release-notes": 2,
    "support": 3,
    "trust": 3,
    "blog": 4,
    "marketing": 4,
    "community": 5,
    "internal": 9,
}

# Documents older than this are demoted two tiers even if the manifest says "current".
# support/faq.md (2023-11-02) is the reason this rule exists. Absolute on purpose: the
# corpus is a snapshot dated 2026, and a relative rule would demote the approved SLA (2025-11)
# the moment the newest document moved forward a year.
STALE_BEFORE = date(2025, 1, 1)
STALE_PENALTY = 2

# Weight applied to a chunk's fused retrieval score. Tier 1 keeps its score; a forum post
# needs to be more than twice as relevant as a policy chunk to outrank it.
TIER_WEIGHT = {1: 1.00, 2: 0.90, 3: 0.75, 4: 0.60, 5: 0.45, 6: 0.40, 7: 0.35, 8: 0.30, 9: 0.0}

PLAN_NAMES = ("starter", "growth", "scale", "enterprise")

# Forum posts by these authors are treated as staff answers. Anchored so a user handle
# containing "ferrowave" does not inherit staff trust.
STAFF_AUTHOR_RE = re.compile(r"^ferrowave (team|staff|support)\b", re.I)

# Topics whose answer is a per-plan table. If the question hits one of these, names no plan
# and is not asking for a comparison, the service asks which plan the customer is on.
# Deliberately narrow: "how much notice", "at scale", "tell us" must not fire.
_PLAN_GATED = [
    r"\bhow many (seats|users|members|responses|requests)\b",
    r"\b(seat|seats) (are |is )?included\b",
    r"\bincluded seats?\b",
    r"\b(price|pricing|cost|costs) (of|for|per)\b",
    r"\bhow much (does|is|do|will|would|are)\b",
    r"\bper (month|year)\b",
    r"\bextra seats?\b",
    r"\boverage\b",
    r"\bresponse (limit|quota|allowance)\b",
    r"\b(my|our)\b.{0,30}\brate limits?\b",
    r"\brate limits? (on|for) my\b",
    r"\brequests per (minute|day)\b",
    r"\b(support )?(response|reply) time\b",
    r"\bhow long .{0,40}\b(keep|retain)\b.{0,40}\b(responses?|data|surveys?)\b",
    r"\bretention (window|period|policy)\b|\bdata retention\b",
    r"\bwebhook (log|logs|delivery log)",
    r"\bincluded in my plan\b|\bon my plan\b",
]
_COMPARISON = re.compile(r"\b(which plans?|each plan|all plans|every plan|compare|difference between|what plans?)\b", re.I)
_PLAN_GATED_RE = [re.compile(p, re.I) for p in _PLAN_GATED]
# A plan is "named" when written as a proper noun, or a lowercase name next to a plan word.
# Plain lowercase "scale" / "growth" are ordinary English ("at scale", "growth in NPS").
_PLAN_PROPER = re.compile(r"\b(Starter|Growth|Scale|Enterprise)\b")
_PLAN_CONTEXT = re.compile(r"\b(starter|growth|scale|enterprise)\s+(plan|workspace|tier|subscription|customers?)\b"
                           r"|\bon (the )?(starter|growth|scale|enterprise)\b", re.I)


def folder_of(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def is_stale(last_updated: str) -> bool:
    """One definition of stale, used for the tier penalty and the context warning."""
    updated = parse_date(last_updated or "")
    return bool(updated and updated < STALE_BEFORE)


def tier_for(row: Dict[str, str]) -> int:
    """Authority tier for a manifest row (1 = highest)."""
    tier = TIER_BY_FOLDER.get(folder_of(row["path"]), 4)
    if is_stale(row.get("last_updated", "")):
        tier += STALE_PENALTY
    notes = (row.get("notes") or "").lower()
    if "marketing page" in notes:
        tier += 1
    if "user generated" in notes:
        tier = max(tier, 5)
    return min(tier, 9)


def customer_visible(row: Dict[str, str]) -> Tuple[bool, str]:
    """Whether a document may ever be shown to a customer, and why not."""
    audience = (row.get("audience") or "").strip().lower()
    status = (row.get("status") or "").strip().lower()
    if audience != "public":
        return False, f"audience={audience or 'missing'}"
    if status in {"draft", "superseded", "archived", "deprecated"}:
        return False, f"status={status}"
    # Another manifest row names this document in its `supersedes` column (set by ingest).
    if row.get("_superseded_by"):
        return False, f"superseded_by={row['_superseded_by']}"
    return True, ""


def mentions_plan(question: str) -> bool:
    return bool(_PLAN_PROPER.search(question) or _PLAN_CONTEXT.search(question))


def plan_gate(question: str) -> str:
    """'force' -> service must ask which plan; 'open' -> model decides status."""
    if mentions_plan(question) or _COMPARISON.search(question):
        return "open"
    if any(rx.search(question) for rx in _PLAN_GATED_RE):
        return "force"
    return "open"


def weight_for_tier(tier: int) -> float:
    return TIER_WEIGHT[max(1, min(int(tier), 9))]
