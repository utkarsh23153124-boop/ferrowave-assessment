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
