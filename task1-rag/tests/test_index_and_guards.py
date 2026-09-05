"""Offline end-to-end: ingest the real corpus without embeddings, retrieve, verify quotes."""
from rag.answer import Citation, quote_in_file, verify_citations

HIDDEN = {
    "pricing/pricing-2024.md",
    "policies/sla-v4-DRAFT.md",
    "internal/rfc-0042-salesforce-v2.md",
    "internal/support-macros.md",
}


def test_ingest_counts(offline_index):
    meta = offline_index.meta
    assert meta["documents"] == 40
    assert meta["documents_customer_visible"] == 36
    assert not [f for f in meta["files"] if f.get("error")]
    hidden = {f["path"] for f in meta["files"] if f.get("visible") is False}
    assert hidden == HIDDEN


def test_hidden_documents_never_retrieved(offline_index):
    for q in ["goodwill credit without manager approval", "99.99% uptime four nines",
              "Meridian renewal Salesforce", "Starter $19 per month"]:
        paths = {d.metadata["path"] for d, _ in offline_index.retrieve(q, k=12)}
        assert not (paths & HIDDEN), f"{q!r} surfaced {paths & HIDDEN}"


def test_policy_outranks_stale_faq(offline_index):
    ranked = [d.metadata["path"] for d, _ in offline_index.retrieve("refund policy money-back guarantee", k=6)]
    assert "policies/refund-policy.md" in ranked
    assert "support/faq.md" in ranked, "the stale FAQ should be a candidate so the ordering is actually exercised"
    assert "support/faq.md" not in ranked[: ranked.index("policies/refund-policy.md")]


def test_quote_verification(offline_index):
    ok = "you may request a full refund of the first month's fee within **14 days** of the first charge"
    assert quote_in_file(offline_index, "policies/refund-policy.md", ok)
    assert quote_in_file(offline_index, "policies/refund-policy.md", ok.replace("**", ""))  # markdown stripped
    assert not quote_in_file(offline_index, "policies/refund-policy.md", "refunds are available within 14 days")
    # Non-prose formats verify against extracted text.
    assert quote_in_file(offline_index, "legal/dpa.docx", "Sub-processor: Kestrel Inference Ltd")
    assert quote_in_file(offline_index, "product-docs/api-rate-limits.html", "Requests per minute: 60")
    assert not quote_in_file(offline_index, "policies/refund-policy.md", "short")


def test_verify_citations_drops_hidden_and_paraphrased(offline_index):
    cits = [
        Citation(path="corpus/policies/refund-policy.md", quote="Monthly renewal charges are not refundable."),
        Citation(path="internal/support-macros.md", quote="goodwill credits up to $50"),
        Citation(path="policies/refund-policy.md", quote="this is not in the file at all, honestly"),
        Citation(path="policies/refund-policy.md", quote="Monthly renewal charges are not refundable."),  # duplicate
    ]
    good, bad = verify_citations(offline_index, cits)
    assert [c.path for c in good] == ["policies/refund-policy.md"]
    assert len(bad) == 2
