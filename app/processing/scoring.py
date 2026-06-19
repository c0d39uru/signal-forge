from sqlmodel import Session

from app.storage.db import engine
from app.storage.models import Event, EventScore

WEIGHTS = {
    "impact": 0.35,
    "urgency": 0.25,
    "novelty": 0.20,
    "confidence": 0.10,
    "liquidity": 0.10,
}

IMPACT_KEYWORDS = {
    "merger_acquisition": 0.9,
    "fda_approval": 0.85,
    "fda_rejection": 0.85,
    "bankruptcy": 0.95,
    "government_contract": 0.8,
    "large_customer_contract": 0.75,
    "earnings_result": 0.7,
    "ceo_change": 0.65,
    "cfo_change": 0.6,
    "layoffs": 0.6,
    "offering_dilution": 0.7,
    "insider_buying": 0.5,
    "insider_selling": 0.45,
    "analyst_upgrade": 0.5,
    "analyst_downgrade": 0.5,
    "share_buyback": 0.45,
    "partnership": 0.4,
    "product_launch": 0.5,
    "earnings_guidance": 0.55,
    "lawsuit": 0.55,
    "unknown": 0.3,
}

URGENCY_KEYWORDS = {
    "fda_approval": 0.9,
    "fda_rejection": 0.9,
    "bankruptcy": 0.95,
    "merger_acquisition": 0.8,
    "earnings_result": 0.75,
    "ceo_change": 0.7,
    "layoffs": 0.65,
    "government_contract": 0.6,
    "analyst_upgrade": 0.5,
    "analyst_downgrade": 0.5,
}


def compute_score(event: Event) -> EventScore:
    impact = _impact_score(event)
    urgency = _urgency_score(event)
    novelty = _novelty_score(event)
    confidence = _confidence_score(event)
    liquidity = _liquidity_score(event)

    final = (
        WEIGHTS["impact"] * impact
        + WEIGHTS["urgency"] * urgency
        + WEIGHTS["novelty"] * novelty
        + WEIGHTS["confidence"] * confidence
        + WEIGHTS["liquidity"] * liquidity
    )

    return EventScore(
        event_id=event.id,
        impact_score=round(impact, 4),
        urgency_score=round(urgency, 4),
        novelty_score=round(novelty, 4),
        confidence_score=round(confidence, 4),
        liquidity_score=round(liquidity, 4),
        final_score=round(final, 4),
        reasoning=_generate_reasoning(event, impact, urgency, novelty, confidence, liquidity),
    )


def score_event(event: Event) -> EventScore:
    score = compute_score(event)
    session = Session(engine)
    session.add(score)
    session.commit()
    session.refresh(score)
    session.close()
    return score


def _impact_score(event: Event) -> float:
    base = IMPACT_KEYWORDS.get(event.event_type.value, 0.3)
    sentiment = abs(event.sentiment_score) if event.sentiment_score else 0
    return min(base * 0.7 + sentiment * 0.3, 1.0)


def _urgency_score(event: Event) -> float:
    base = URGENCY_KEYWORDS.get(event.event_type.value, 0.4)
    return min(base, 1.0)


def _novelty_score(event: Event) -> float:
    session = Session(engine)
    from sqlmodel import select

    similar = session.exec(
        select(Event).where(
            Event.ticker == event.ticker,
            Event.event_type == event.event_type,
        )
    ).all()
    session.close()

    if len(similar) <= 1:
        return 0.8

    return max(0.2, 0.8 - (len(similar) - 1) * 0.15)


def _confidence_score(event: Event) -> float:
    return event.confidence_score if event.confidence_score else 0.5


def _liquidity_score(event: Event) -> float:
    large_caps = {"AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "WMT"}
    mid_caps = {"COIN", "SQ", "SNOW", "PLTR", "RIVN", "LCID", "SOFI", "AFRM"}

    ticker = event.ticker.upper() if event.ticker else ""
    if ticker in large_caps:
        return 0.9
    elif ticker in mid_caps:
        return 0.6
    return 0.4


def _generate_reasoning(event: Event, impact: float, urgency: float, novelty: float, confidence: float, liquidity: float) -> str:
    return (
        f"Event type {event.event_type.value} for {event.ticker}: "
        f"impact={impact:.2f}, urgency={urgency:.2f}, novelty={novelty:.2f}, "
        f"confidence={confidence:.2f}, liquidity={liquidity:.2f}"
    )