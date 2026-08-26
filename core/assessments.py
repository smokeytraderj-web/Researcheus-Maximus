"""Client-facing labels for specialist evidence behind one overall rating."""

from __future__ import annotations

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
