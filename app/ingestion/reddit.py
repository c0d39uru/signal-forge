import hashlib
from datetime import datetime, timezone

from sqlmodel import Session

from app.config import settings
from app.storage.db import engine
from app.storage.models import RedditMention, ProcessingRun

DEFAULT_SUBREDDITS = ["stocks", "investing", "wallstreetbets"]
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]


def ingest_reddit(
    subreddits: list[str] | None = None,
    tickers: list[str] | None = None,
) -> ProcessingRun:
    run = ProcessingRun(source="reddit", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    subs = subreddits or DEFAULT_SUBREDDITS
    tickers_to_track = tickers or DEFAULT_TICKERS

    try:
        reddit = _get_reddit_client()
        if reddit is None:
            run.status = "skipped: praw not configured"
            run.finished_at = datetime.now(timezone.utc)
            session.add(run)
            session.commit()
            session.close()
            return run

        for sub_name in subs:
            subreddit = reddit.subreddit(sub_name)
            for ticker in tickers_to_track:
                try:
                    mentions = 0
                    sentiment_sum = 0.0

                    for submission in subreddit.search(f"${ticker}", sort="new", time_filter="day", limit=25):
                        mentions += 1
                        sentiment_sum += _crude_sentiment(submission.title + " " + (submission.selftext or ""))

                    avg_sentiment = sentiment_sum / mentions if mentions > 0 else 0.0

                    mention = RedditMention(
                        ticker=ticker,
                        subreddit=sub_name,
                        mention_count=mentions,
                        sentiment_estimate=round(avg_sentiment, 3),
                        mention_velocity=float(mentions),
                    )
                    session.add(mention)
                    run.items_fetched += 1
                except Exception:
                    run.items_skipped += 1
                    continue

        session.commit()
        run.status = "completed"
    except Exception as e:
        run.status = f"failed: {e}"
    finally:
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        session.close()

    return run


def _get_reddit_client():
    if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
        return None
    try:
        import praw

        return praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
        )
    except ImportError:
        return None


def _crude_sentiment(text: str) -> float:
    positive = ["bullish", "buy", "up", "growth", "profit", "beat", "upgrade", "strong"]
    negative = ["bearish", "sell", "down", "loss", "miss", "downgrade", "weak", "crash"]

    text_lower = text.lower()
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)

    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)