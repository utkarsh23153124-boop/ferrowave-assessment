from rag.policy import customer_visible, mentions_plan, plan_gate, tier_for


def row(path, audience="public", status="current", updated="2026-03-01", notes="", superseded_by=""):
    return {"path": path, "audience": audience, "status": status, "last_updated": updated, "notes": notes,
            "_superseded_by": superseded_by}


def test_internal_draft_superseded_are_hidden():
    assert customer_visible(row("internal/support-macros.md", audience="internal")) == (False, "audience=internal")
    assert customer_visible(row("policies/sla-v4-DRAFT.md", audience="internal", status="draft"))[0] is False
    assert customer_visible(row("pricing/pricing-2024.md", status="superseded")) == (False, "status=superseded")
    assert customer_visible(row("policies/refund-policy.md")) == (True, "")


def test_supersedes_column_hides_the_old_document_even_if_its_status_was_not_updated():
    ok, why = customer_visible(row("pricing/pricing-2026.md", status="current", superseded_by="pricing/pricing-2027.md"))
    assert ok is False and why == "superseded_by=pricing/pricing-2027.md"


def test_tiers():
    assert tier_for(row("policies/refund-policy.md")) == 1
    assert tier_for(row("product-docs/webhooks.md")) == 2
    assert tier_for(row("support/help-center-billing.md")) == 3
    assert tier_for(row("support/faq.md", updated="2023-11-02")) == 5, "stale FAQ demoted below blog"
    assert tier_for(row("trust/security.md", updated="2025-10-01", notes="Marketing page")) == 4
    assert tier_for(row("community/forum-x.md", notes="User generated")) == 5
    assert tier_for(row("internal/rfc.md", audience="internal")) == 9


def test_plan_gate_fires_on_per_plan_facts_without_a_plan():
    for q in ["How many seats do I get?", "What is the support response time?", "What are my API rate limits?",
              "How long do you keep my survey responses?", "How much does Pulse cost per month?"]:
        assert plan_gate(q) == "force", q


def test_plan_gate_stays_open_when_a_plan_is_named_or_compared():
    for q in ["How many seats are included on the Scale plan?", "Which plans include SSO?",
              "What is the price of the growth plan?", "How many responses do I get on enterprise?"]:
        assert plan_gate(q) == "open", q


def test_plan_gate_ignores_ordinary_english():
    for q in ["Which channels can I use to deliver a survey?", "Which events can webhooks send to us?",
              "What happens when I hit the rate limit?", "How much notice do you give before removing an API version?",
              "How long are backups kept?", "Do you offer a Data Processing Addendum for EU customers?",
              "Is there a cost to cancel my subscription?", "What uptime does the SLA commit to?"]:
        assert plan_gate(q) == "open", q


def test_common_words_scale_and_growth_do_not_count_as_plan_names():
    assert not mentions_plan("How many responses per month can I collect at scale?")
    assert not mentions_plan("Do you track growth in NPS over time?")
    assert mentions_plan("How many responses per month on the scale plan?")
    assert mentions_plan("What does Growth include?")
    assert plan_gate("How many responses per month can I collect at scale?") == "force"
