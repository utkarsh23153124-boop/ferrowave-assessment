from rag.answer import fallback_citation, quote_in_file


def test_fallback_picks_overlapping_sentence_and_verifies(offline_index):
    hits = offline_index.retrieve("What is the target support response time on the Growth plan?", k=8)
    fb = fallback_citation("The target support response time for the Growth plan is two business days for email support.", hits)
    assert fb is not None
    assert fb.path == "product-docs/plans-and-features.md"
    assert "two business day" in fb.quote
    assert quote_in_file(offline_index, fb.path, fb.quote)


def test_fallback_refuses_unrelated_answer(offline_index):
    hits = offline_index.retrieve("What is the target support response time on the Growth plan?", k=8)
    assert fallback_citation("Bananas are yellow and grow in bunches on trees.", hits) is None


def test_fallback_never_cites_stale_or_low_tier_pages(offline_index):
    """A negating answer overlaps best with the stale FAQ sentence it contradicts; code must not attach it."""
    hits = offline_index.retrieve("Do you offer a 30-day money-back guarantee?", k=8)
    assert any(d.metadata["path"] == "support/faq.md" for d, _ in hits), "test needs the FAQ as a candidate"
    answer = ("No, we do not offer a 30-day no-questions-asked money-back guarantee on all plans. "
              "Monthly plans may request a full refund of the first month within 14 days.")
    fb = fallback_citation(answer, hits)
    assert fb is None or fb.path != "support/faq.md"


def test_fallback_is_restricted_to_documents_the_model_cited(offline_index):
    hits = offline_index.retrieve("What is the target support response time on the Growth plan?", k=8)
    answer = "The target support response time for the Growth plan is two business days for email support."
    assert fallback_citation(answer, hits, cited_paths={"pricing/plans.json"}) is None
    assert fallback_citation(answer, hits, cited_paths={"product-docs/plans-and-features.md"}) is not None
