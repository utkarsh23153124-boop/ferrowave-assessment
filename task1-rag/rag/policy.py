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
# support/faq.md (2023-11-02) is the reason this rule exists.
STALE_BEFORE = date(2025, 1, 1)
STALE_PENALTY = 2

# Weight applied to a chunk's fused retrieval score. Tier 1 keeps its score; a forum post
# needs to be more than twice as relevant as a policy chunk to outrank it.
TIER_WEIGHT = {1: 1.00, 2: 0.90, 3: 0.75, 4: 0.60, 5: 0.45, 6: 0.40, 7: 0.35, 8: 0.30, 9: 0.0}

PLAN_NAMES = ("starter", "growth", "scale", "enterprise")

# Topics whose answer changes by plan. If the question hits one of these and names no plan
# and is not asking for a comparison, the service asks which plan the customer is on.
_PLAN_GATED = [
    r"\bhow many (seats|users|responses|requests)\b",
    r"\b(seat|seats) (are |is )?included\b",
    r"\bincluded seats?\b",
    r"\b(price|pricing|cost|costs|how much|per month|per year|monthly|annual(ly)?)\b",
    r"\bextra seat",
    r"\boverage\b",
    r"\bresponse (limit|quota|allowance)\b",
    r"\brate limit",
    r"\brequests per (minute|day)\b",
    r"\b(support )?(response|reply) time\b",
    r"\bhow (long|many (days|months)).{0,40}\b(keep|retain|retention|stored|kept)\b",
    r"\bretention\b",
    r"\bwebhook (log|logs|delivery log)",
    r"\b(eu|european|us|region|data residency|where is my data)\b",
]
_PLAN_GATED.append(r"included in my plan|on my plan")
_COMPARISON = re.compile(r"\b(which plans?|each plan|all plans|every plan|compare|difference between|what plans?)\b", re.I)
_PLAN_GATED_RE = [re.compile(p, re.I) for p in _PLAN_GATED]


def folder_of(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


def parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except Exception:
        return None


def tier_for(row: Dict[str, str]) -> int:
    """Authority tier for a manifest row (1 = highest)."""
    tier = TIER_BY_FOLDER.get(folder_of(row["path"]), 4)
    updated = parse_date(row.get("last_updated", ""))
    if updated and updated < STALE_BEFORE:
        tier += STALE_PENALTY
    if "marketing page" in (row.get("notes") or "").lower():
        tier += 1
    if "user generated" in (row.get("notes") or "").lower():
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
    return True, ""


def mentions_plan(question: str) -> bool:
    q = question.lower()
    return any(re.search(rf"\b{p}\b", q) for p in PLAN_NAMES)


def plan_gate(question: str) -> str:
    """'force' -> service must ask which plan; 'open' -> model decides status."""
    if mentions_plan(question) or _COMPARISON.search(question):
        return "open"
    if any(rx.search(question) for rx in _PLAN_GATED_RE):
        return "force"
    return "open"


def weight_for_tier(tier: int) -> float:
    return TIER_WEIGHT.get(tier, 0.3)
