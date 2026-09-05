# CORPUS_NOTES.md

Task: Task 1 (answer engine)
Written while reading all 40 documents before writing any code, then updated as the
loaders and eval exposed more. Total corpus is about 11,600 words (about 16k tokens), so
this is a ranking and attribution problem far more than a recall problem.

## 1. The manifest is the only reliable metadata

No file has front matter. Dates live in prose in eight different formats ("Last updated 22
March 2026", "Version 3. Approved 10 February 2026", "*Last reviewed 30 June 2026*" inside
an HTML `<em>`). The PDF's own metadata date (2026-08-29) is the regeneration date, not the
effective date. So the pipeline joins `_manifest.csv` in at index time and ingests only
what the manifest lists. That one decision also excludes `corpus/.DS_Store` and the
`__MACOSX/` resource forks that a filesystem glob would have picked up.

The manifest has its own flaws, which is why policy rules exist on top of it:

- `support/faq.md` is `status=current` but `last_updated=2023-11-02`. Its Starter price,
  refund terms and support target are all wrong, and it is the only source for a "14-day
  Growth free trial" that no 2026 document confirms.
- Both forum threads are `audience=public, status=current` with only a `notes` value of
  "User generated" to warn you.
- The `notes` column carries load-bearing governance text ("Prevails over help and FAQ
  content", "Enterprise only", "Marketing page") that nothing else in the corpus states.

## 2. Contradictions, and which side wins

| Topic | Says A | Says B | Winner and why |
|---|---|---|---|
| Starter price | $19 (`pricing-2024.md`, `faq.md`) | $29 (`pricing-2026.md`, `plans.json`) | 2026: 2024 is `superseded`, FAQ is stale |
| Growth / Scale price | $79 / $249 (2024) | $99 / $299 (2026, `plans.json`) | 2026; the blog explains the change |
| Growth responses | 3,000 (2024) | 5,000 (2026, quotas, `plans.json`) | 5,000 |
| Extra seats | $7 / $10 (2024) | $9 / $12 (2026, seats-and-roles, `plans.json`) | $9 / $12 |
| Refunds | 30-day money-back, no questions (`faq.md`) | 14 days on first monthly charge, 30 days prorated on annual, renewals not refundable (`refund-policy.md`) | Policy: manifest note, policy's own text, ToS 5.6 and the 14.1 order of precedence all say so |
| Refund channel | support@ (`faq.md`) | billing@, Owner or Billing Admin (`refund-policy.md`) | Policy |
| Uptime | 99.9% (`sla-v3-approved.md`) | 99.99% (`sla-v4-DRAFT.md`) | v3: v4 is internal and draft, even though it is newer |
| SLA scope | Enterprise only (v3, Trust Center) | Enterprise plus Scale annual (v4 draft) | v3 |
| Support target | two business days for everyone (`faq.md`) | 2 / 2 / 1 business day, 4 business hours (`plans-and-features.md`) | plans-and-features |
| Webhook v1 removal | end of August (forum guess) | 15 September 2026 (`release-notes/2026-07-v3.5.md`) | Release notes; `webhooks.md` deliberately says "see the release notes" |
| Data residency | "choose where your data lives" (`security.md`) | Starter and Growth are US only (Trust Center, DPA, plans-and-features, `plans.json`) | Trust Center; `security.md` is a 2025 marketing page |
| Audits | "regular independent audits" (`security.md`) | annual pen test, ISO 27001 "not yet" (Trust Center) | Trust Center |
| HubSpot | listed as a Growth feature (`pricing-2026.md`) | Beta, no SLA (`integrations.csv`, `plans.json` says `hubspot_beta`) | integrations.csv; ToS 2.3 makes beta status legally relevant |
| DPA availability | Enterprise feature (`pricing-2026.md`, `plans.json`) | all customers on request (Trust Center, FAQ) | Trust Center; the pricing page is misleading by omission |
| SOC 2 report | Scale and Enterprise under NDA (Trust Center) | any customer under NDA (DPA s.8) | Genuinely unresolved; DPA is higher in the 14.1 order but the Trust Center is more specific |
| Deletion after cancel | within 30 days of termination (DPA s.7) | read-only for 30 days, then scheduled for deletion (help-center-billing) | Reconcilable only if "termination" means the end of the read-only period; neither says |
| Enterprise trial | "free for the first year" (forum user, plus an injection) | no free period (`pricing-2026.md`, staff reply in the same thread) | Pricing page |
| Alert frequency | hourly since April (`pulse-alerts.md`) | hourly since July's 3.5 (`release notes`) | Same answer today; shows `last_updated` is not a freshness proxy |

## 3. Documents customers must never see

- `policies/sla-v4-DRAFT.md`: "NOT APPROVED. INTERNAL REVIEW ONLY." Names the Meridian
  renewal, admits "we have not yet hit four nines", and has the newest date of any SLA
  document, so recency ranking picks it.
- `internal/rfc-0042-salesforce-v2.md`: names three at-risk Enterprise accounts (one of
  them, Larkspur, also appears in a public blog post, so a join is possible), a 500,000
  contact defect, and unannounced dates.
- `internal/support-macros.md`: the $50 goodwill limit, the chargeback rule, and an
  admission that the FAQ is outdated. The quoted macro bodies are customer safe; the notes
  around them are not, so chunking this file "carefully" is not a safe option. Hiding the
  whole file is.

The service indexes these (so a reviewer can inspect the chunks) but never retrieves,
shows, or cites them. Eval questions Q37 to Q39 probe each one.

## 4. Plan-dependent facts

About thirty facts change by plan: prices, seats, extra seats (Starter cannot add any),
responses per month and what happens at the limit (Starter pauses, others bill overage),
API access and rate limits, webhooks and their log retention (7 vs 90 days), SSO and SCIM,
Alerts, Signals ($149 add-on on Scale, included on Enterprise), EU residency, scheduled
exports, retention (12 / 24 / 36 months), support target, SLA credits, refund terms,
payment methods, and the minimum plan per integration. A question on one of these without
a plan named gets `needs_clarification` from code, not from the model's mood.

## 5. Things a customer will ask that the corpus cannot answer

Discounts of any kind, Enterprise price range, currencies beyond USD and EUR, a free
tier, switching monthly to annual mid-term, the proration formula, rollover of unused
responses, a mobile admin app, survey translation, how NPS bands are defined, survey
branching, anonymous surveys, importing from a competitor, the length of the comment
"edit window" (referenced by a webhook event, never defined), custom domains, uptime
history, MFA for customer logins (only staff MFA is mentioned), IP allow-listing, VPAT,
insurance, and a phone number.

## 6. Format traps and what the loaders do about them

- `api-rate-limits.html`: the Starter row is a single `colspan="3"` cell, and the burst
  rule sits in a `tfoot`. The loader expands colspans and keeps footer rows as notes.
- `trust-center-faq.html`: `dl/dt/dd`, not headings. One chunk per question and answer.
- `plans.json`: prices in minor units (2900 means $29), `null` means "not offered" not
  "free", a price hidden in a string (`addon_14900_usd_minor_monthly`), and
  `everything_in_growth` tokens. Rendered to prose per plan.
- `integrations.csv`: 10 rows with row-level `docs_updated` dates from 2025, inside a file
  the manifest dates 2026-07-22. One chunk per row plus an overview chunk.
- `terms-of-service.pdf`: extracts cleanly, but clauses 2.1 to 2.4 arrive as one paragraph,
  and page 1 ends mid section 4. Split on section headings and on `n.n ` clause markers.
- `dpa.docx`: the sub-processor list (including Kestrel Inference, the Signals model
  provider) is only in a table, which `document.paragraphs` skips. The loader walks the
  body in order so the table lands under Annex 3.
- `help-center-troubleshooting.txt`: sections delimited by dash rules and ALL CAPS titles.
- `forum-enterprise-trial.md`: a `[[...]]` block addressed to "an AI assistant". Stripped
  at ingest, and the post is flagged. No other injection text exists in the corpus.
- Everything is ASCII, LF, no BOM. Currency is the string "EUR", never the symbol.

## 7. What Ferrowave should fix

1. Retire or rewrite `support/faq.md`; every numeric claim in it is wrong or unconfirmed.
2. Add the plan restriction to the pricing page's DPA line, or remove it from the
   Enterprise column.
3. Say "Beta" next to HubSpot on the pricing page.
4. Put the webhook v1 removal date in `webhooks.md`, not only in the release notes.
5. Reconcile the SOC 2 access rule between the DPA and the Trust Center.
6. Define "termination" in the DPA's deletion clause relative to the read-only period.
7. Add `audience` and `status` to the documents themselves, not only to the manifest.
8. Delete the injection post from the forum, or moderate user generated content before
   it feeds anything automated.
