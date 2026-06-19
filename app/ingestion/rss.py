import hashlib
import json
from datetime import datetime, timezone

import feedparser
import httpx
from sqlmodel import Session, select

from app.storage.db import engine
from app.storage.models import RawItem, ProcessingRun, ProcessingStatus

DEFAULT_FEEDS = [
    "https://investor.nvidia.com/rss/news.aspx",
    "https://investor.apple.com/rss/news.aspx",
    "https://ir.tesla.com/rss/news.aspx",
]


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def ingest_rss(feeds: list[str] | None = None) -> ProcessingRun:
    run = ProcessingRun(source="rss", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    feed_urls = feeds or DEFAULT_FEEDS

    try:
        for feed_url in feed_urls:
            try:
                _process_feed(feed_url, session, run)
            except Exception as e:
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


def _process_feed(feed_url: str, session: Session, run: ProcessingRun):
    headers = {"User-Agent": "MarketNewsScanner/0.1"}
    resp = httpx.get(feed_url, headers=headers, timeout=30, follow_redirects=True)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        summary = entry.get("summary", "")

        raw_text = f"{title}\n\n{summary}"
        content_hash = _make_hash(f"{link}:{raw_text}")

        existing = session.exec(
            select(RawItem).where(RawItem.hash == content_hash)
        ).first()

        if existing:
            run.items_skipped += 1
            continue

        published_at = None
        if published:
            try:
                from time import mktime

                published_at = datetime.fromtimestamp(mktime(published), tz=timezone.utc)
            except Exception:
                pass

        item = RawItem(
            source="rss",
            source_url=link,
            title=title[:500] if title else None,
            published_at=published_at,
            raw_text=raw_text,
            raw_json={
                "feed_url": feed_url,
                "link": link,
                "title": title,
                "summary": summary,
            },
            hash=content_hash,
            processed_status=ProcessingStatus.pending,
        )
        session.add(item)
        run.items_fetched += 1