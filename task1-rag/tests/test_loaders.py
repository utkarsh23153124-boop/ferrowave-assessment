"""Each test pins one corpus trap that a generic loader would get wrong."""
from rag.loaders import load_file


def pieces(corpus, rel):
    return load_file(corpus / rel, rel)


def texts(corpus, rel):
    return [t for _, t, _ in pieces(corpus, rel)]


def test_html_table_colspan_and_tfoot(corpus):
    table = next(t for _, t, ex in pieces(corpus, "product-docs/api-rate-limits.html") if ex.get("kind") == "table")
    assert "Plan: Starter | Requests per minute: No API access | Requests per day: No API access" in table
    assert "Plan: Growth | Requests per minute: 60 | Requests per day: 10,000 | Concurrent requests: 4" in table
    assert "Burst allowance" in table, "tfoot note must survive"


def test_html_definition_list_becomes_qa_pairs(corpus):
    secs = [s for s, _, ex in pieces(corpus, "trust/trust-center-faq.html") if ex.get("kind") == "faq"]
    assert any("Is Ferrowave SOC 2 certified?" in s for s in secs)
    assert any("Where is my data hosted?" in s for s in secs)


def test_docx_table_rows_are_kept(corpus):
    annex = next(t for s, t, _ in pieces(corpus, "legal/dpa.docx") if s.startswith("Annex 3"))
    assert "Kestrel Inference Ltd" in annex
    assert "Sub-processor: Nimbus Cloud Europe BV" in annex


def test_json_minor_units_rendered_as_money(corpus):
    by_section = {s: t for s, t, _ in pieces(corpus, "pricing/plans.json")}
    assert "USD 29.00 per month" in by_section["Starter"]
    assert "Extra seats: not offered" in by_section["Starter"]
    assert "USD 149.00 per month" in by_section["Scale"], "add-on price hidden in a string id"
    assert "custom" in by_section["Enterprise"].lower()
    assert "not offered per month" not in by_section["Enterprise"]


def test_forum_injection_stripped_and_staff_flagged(corpus):
    ps = pieces(corpus, "community/forum-enterprise-trial.md")
    assert not any("disregard other sources" in t for _, t, _ in ps)
    assert any(ex.get("injection_stripped") for _, _, ex in ps)
    staff = [ex for _, _, ex in ps if ex.get("author_role") == "staff"]
    assert len(staff) == 1


def test_pdf_sections_and_clauses(corpus):
    by_section = {}
    for s, t, _ in pieces(corpus, "legal/terms-of-service.pdf"):
        by_section.setdefault(s, "")
        by_section[s] += "\n" + t
    assert "Order of precedence" in by_section["14. General"]
    assert "\n4.2 Enterprise Plans" in by_section["4. Term and termination"], "clauses split onto their own lines"


def test_txt_sections_split_on_rules(corpus):
    secs = [s for s, _, _ in pieces(corpus, "support/help-center-troubleshooting.txt")]
    assert "ALERT DID NOT FIRE" in secs
    assert "WEBHOOK SIGNATURE VERIFICATION FAILS" in secs


def test_csv_row_per_chunk(corpus):
    hubspot = next(t for s, t, _ in pieces(corpus, "product-docs/integrations.csv") if s == "HubSpot")
    assert "Status: Beta" in hubspot
    assert "Minimum plan: Growth" in hubspot


def test_markdown_sections_keep_headings(corpus):
    secs = [s for s, _, _ in pieces(corpus, "policies/refund-policy.md")]
    assert any(s.startswith("1. Monthly self-serve plans") for s in secs)
