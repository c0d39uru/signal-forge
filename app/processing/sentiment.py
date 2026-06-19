import re

POSITIVE_WORDS = {
    "bullish", "buy", "up", "growth", "profit", "beat", "upgrade",
    "strong", "gain", "positive", "rally", "surge", "record", "high",
    "exceed", "outperform", "raise", "boost", "soar", "jump",
}

NEGATIVE_WORDS = {
    "bearish", "sell", "down", "loss", "miss", "downgrade", "weak",
    "decline", "negative", "drop", "fall", "crash", "low", "cut",
    "underperform", "reduce", "slump", "plunge", "warn", "risk",
}


def sentiment_from_text(text: str) -> float:
    if not text:
        return 0.0

    words = re.findall(r"\b\w+\b", text.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)

    total = pos + neg
    if total == 0:
        return 0.0

    return round((pos - neg) / total, 4)