from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlmodel import Session, select

from app.storage.db import get_session, init_db
from app.storage.models import Event, EventScore, RedditMention

app = FastAPI(title="Market News Scanner", version="0.1.0")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/events/recent")
def recent_events(limit: int = 50, session: Session = Depends(get_session)):
    events = session.exec(
        select(Event).order_by(Event.created_at.desc()).limit(limit)
    ).all()
    return [_serialize_event(e, session) for e in events]


@app.get("/events/top")
def top_events(
    since: str = Query("24h", description="Time window: e.g. 24h, 48h, 7d"),
    min_score: float = Query(0.7, description="Minimum final score"),
    limit: int = Query(50),
    session: Session = Depends(get_session),
):
    since_dt = _parse_since(since)
    events = session.exec(
        select(Event).where(Event.created_at >= since_dt).order_by(Event.created_at.desc())
    ).all()

    results = []
    for event in events:
        score = session.exec(
            select(EventScore).where(EventScore.event_id == event.id)
        ).first()
        if score and score.final_score >= min_score:
            results.append({**_serialize_event(event, session), "score": _serialize_score(score)})

    results.sort(key=lambda x: x.get("score", {}).get("final_score", 0), reverse=True)
    return results[:limit]


@app.get("/events/{event_id}")
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _serialize_event(event, session)


@app.get("/tickers/{ticker}/events")
def ticker_events(
    ticker: str,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    events = session.exec(
        select(Event)
        .where(Event.ticker == ticker.upper())
        .order_by(Event.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialize_event(e, session) for e in events]


def _serialize_event(event: Event, session: Session) -> dict:
    score = session.exec(
        select(EventScore).where(EventScore.event_id == event.id)
    ).first()
    return {
        "id": event.id,
        "ticker": event.ticker,
        "event_type": event.event_type.value if event.event_type else None,
        "summary": event.summary,
        "sentiment_score": event.sentiment_score,
        "confidence_score": event.confidence_score,
        "extracted_facts": event.extracted_facts_json,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "score": _serialize_score(score) if score else None,
    }


def _serialize_score(score: EventScore) -> dict:
    return {
        "id": score.id,
        "impact_score": score.impact_score,
        "urgency_score": score.urgency_score,
        "novelty_score": score.novelty_score,
        "confidence_score": score.confidence_score,
        "liquidity_score": score.liquidity_score,
        "final_score": score.final_score,
        "reasoning": score.reasoning,
    }


def _parse_since(since: str) -> datetime:
    now = datetime.now(timezone.utc)
    try:
        if since.endswith("h"):
            hours = int(since[:-1])
            return now - timedelta(hours=hours)
        elif since.endswith("d"):
            days = int(since[:-1])
            return now - timedelta(days=days)
    except ValueError:
        pass
    return now - timedelta(hours=24)