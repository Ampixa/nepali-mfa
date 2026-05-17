"""Small transcript repair helpers used after manual MFA review."""

from __future__ import annotations


_ONE_THOUSAND_NINE_HUNDRED = "एक हजार नौ सय"
_NINETEEN_HUNDRED = "उन्नाइस सय"


def rewrite_1900s_cardinal_phrase_to_year_style(text: str) -> str:
    """Rewrite spelled-out 1900s cardinal phrases to year-style speech.

    This is intentionally a review-time repair, not a blanket normalizer.
    """

    if _ONE_THOUSAND_NINE_HUNDRED not in text:
        return text
    return text.replace(_ONE_THOUSAND_NINE_HUNDRED, _NINETEEN_HUNDRED)
