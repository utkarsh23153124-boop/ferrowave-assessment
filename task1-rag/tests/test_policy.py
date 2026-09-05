from rag.policy import customer_visible, plan_gate, tier_for


def row(path, audience="public", status="current", updated="2026-03-01", notes=""):
    return {"path": path, "audience": audience, "status": status, "last_updated": updated, "notes": notes}


def test_internal_draft_superseded_are_hidden():
    assert customer_visible(row("internal/support-macros.md", audience="internal")) == (False, "audience=internal")
    assert customer_visible(row("policies/sla-v4-DRAFT.md", audience="internal", status="draft"))[0] is False
    assert customer_visible(row("pricing/pricing-2024.md", status="superseded")) == (False, "status=superseded")
    assert customer_visible(row("policies/refund-policy.md")) == (True, "")


def test_tiers():
    assert tier_for(row("policies/refund-policy.md")) == 1
    assert tier_for(row("product-docs/webhooks.md")) == 2
    assert tier_for(row("support/help-center-billing.md")) == 3
    assert tier_for(row("support/faq.md", updated="2023-11-02")) == 5, "stale FAQ demoted below blog"
    assert tier_for(row("trust/security.md", updated="2025-10-01", notes="Marketing page")) == 4
    assert tier_for(row("community/forum-x.md", notes="User generated")) == 5
    assert tier_for(row("internal/rfc.md", audience="internal")) == 9


def test_plan_gate():
    assert plan_gate("How many seats do I get?") == "force"
    assert plan_gate("What is the target support response time?") == "force"
    assert plan_gate("How many seats are included on the Scale plan?") == "open"
    assert plan_gate("Which plans include SSO?") == "open"
    assert plan_gate("Which channels can I use to deliver a survey?") == "open"
    assert plan_gate("Which events can webhooks send?") == "open"
