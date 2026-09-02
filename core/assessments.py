"""Client-facing labels for specialist evidence behind one overall rating."""

from __future__ import annotations

import re

from core.models import Rating


_POSITIVE = {Rating.STRONG_BUY, Rating.BUY, Rating.ADD}
_NEGATIVE = {Rating.REDUCE, Rating.SELL, Rating.AVOID}


def technical_setup(rating: Rating) -> str:
    """Translate an internal recommendation-scale score into chart language."""
    if rating in _POSITIVE:
        return "Bullish"
    if rating in _NEGATIVE:
        return "Bearish"
    return "Neutral"


def fundamental_outlook(rating: Rating) -> str:
    """Translate an internal recommendation-scale score into business-outlook language."""
    if rating in _POSITIVE:
        return "Positive"
    if rating in _NEGATIVE:
        return "Negative"
    return "Balanced"


def assessment_interpretation(technical_rating: Rating, fundamental_rating: Rating) -> str:
    """Reconcile the two supporting lenses in plain client-ready language."""
    technical = technical_setup(technical_rating)
    fundamental = fundamental_outlook(fundamental_rating)
    interpretations = {
        ("Bullish", "Positive"): "The business outlook and current entry setup are both constructive.",
        ("Neutral", "Positive"): "The underlying company outlook is positive, while the current entry setup is neutral.",
        ("Bearish", "Positive"): "Good underlying company, but the current entry setup is weak.",
        ("Bullish", "Balanced"): "The current entry setup is constructive, while the fundamental outlook is balanced.",
        ("Neutral", "Balanced"): "Neither the business outlook nor the current entry setup provides a strong directional signal.",
        ("Bearish", "Balanced"): "The fundamental outlook is balanced, but the current entry setup is weak.",
        ("Bullish", "Negative"): "The chart is constructive, but weaker fundamentals limit conviction.",
        ("Neutral", "Negative"): "The current entry setup is neutral, while the fundamental outlook remains weak.",
        ("Bearish", "Negative"): "Both the fundamental outlook and current entry setup are weak.",
    }
    return interpretations[(technical, fundamental)]

# Providers prefix their conclusion prose with a machine-style label
# ("Direct answer:", "Overall conclusion:"). Those labels existed to head a
# dedicated block; where the prose is rendered as ordinary copy the prefix is
# noise, so both renderers strip it through here.
_CONCLUSION_PREFIXES = (
    "Overall conclusion:",
    "Direct answer:",
    "Position answer:",
    "Portfolio-fit answer:",
    "Historical conclusion:",
    "Historical case-study answer:",
)


def strip_conclusion_prefix(value: str) -> str:
    """The conclusion prose without its machine-style leading label."""
    cleaned = value.strip()
    for prefix in _CONCLUSION_PREFIXES:
        if cleaned.lower().startswith(prefix.lower()):
            return cleaned[len(prefix):].lstrip()
    return cleaned


# Sentences the reasoning prose repeats from elsewhere on the page, or that
# expose how the answer was produced rather than what it is. Both are dead
# weight in a "Why" block: the reader has just seen the rating at display size,
# the setup and outlook in the strip above, and should never be shown the
# internal weighting at all.
_METHOD_MARKERS = (
    "framework weights",
    "weights fundamental evidence",
    "weights technical evidence",
    "evidence 50%",
    "horizon weighting",
)
_RESTATEMENT_PATTERNS = (
    # "Apple Inc. receives a Buy rating for the medium term horizon."
    re.compile(r"\breceives?\s+an?\s+[\w\s]{2,20}\s+rating\b", re.IGNORECASE),
    # "The technical setup is bullish, and the fundamental outlook is positive."
    re.compile(r"^\s*the\s+(technical\s+setup|fundamental\s+outlook)\s+is\b", re.IGNORECASE),
    # "The business outlook and current entry setup are both constructive."
    re.compile(r"^\s*the\s+business\s+outlook\s+and\b.*\bare\s+both\b", re.IGNORECASE),
)


# Periods that do not end a sentence. Splitting naively on ". " turned
# "Apple Inc. receives a Buy rating." into two, dropped the half that carried
# the verb, and left "Apple Inc." stranded as its own line.
_ABBREVIATIONS = (
    "Inc.", "Corp.", "Co.", "Ltd.", "L.P.", "LLC.", "plc.", "S.A.", "N.V.",
    "Jr.", "Sr.", "St.", "No.", "Nos.", "Est.", "Approx.", "vs.", "etc.",
    "U.S.", "U.K.", "E.U.", "a.m.", "p.m.", "Q1.", "Q2.", "Q3.", "Q4.",
)
_ABBREV_GUARD = "\u0000"


def _split_sentences(text: str) -> list[str]:
    """Sentence split that survives "Inc." and friends."""
    protected = text
    for abbreviation in _ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", _ABBREV_GUARD))
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [part.replace(_ABBREV_GUARD, ".") for part in parts]


def condense_reasoning(value: str) -> str:
    """Reasoning prose with restatement and methodology removed.

    Keeps every sentence that carries a figure, a level or a condition -- the
    parts that actually explain the view -- and drops the ones that repeat what
    the masthead, the rating and the metrics strip have already said. If the
    filter would empty the text, the original is returned: a thin "Why" is worse
    than a repetitive one, and this must never silently delete the whole answer.
    """
    text = strip_conclusion_prefix(value)
    if not text:
        return ""
    sentences = _split_sentences(text)
    kept = []
    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(marker in lowered for marker in _METHOD_MARKERS):
            continue
        if any(pattern.search(stripped) for pattern in _RESTATEMENT_PATTERNS):
            continue
        kept.append(stripped)
    return " ".join(kept) if kept else text
