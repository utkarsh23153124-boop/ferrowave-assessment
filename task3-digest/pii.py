"""
PII Redaction module for customer comments before LLM processing.
Redacts phone numbers, email addresses, and payment card references.
"""

import re


EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Matches international and national phone formats like:
# +91 98765 43210, +1 (415) 555-0134, 087 234 5566, (415) 555-0134
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,5}[-.\s]?\d{4,5}\b"
)

# Matches card references like "Card ending 4242"
CARD_REGEX = re.compile(r"\b(?:card ending|ending in|card #?)\s*\d{4}\b", re.IGNORECASE)


def redact_pii(text: str) -> str:
    """
    Replaces sensitive information (emails, phone numbers, card endings)
    with sanitized placeholders [REDACTED_EMAIL], [REDACTED_PHONE], etc.
    """
    if not text:
        return text

    sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    sanitized = CARD_REGEX.sub("[REDACTED_CARD]", sanitized)
    sanitized = PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)

    return sanitized
