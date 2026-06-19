import hashlib
import json
from datetime import datetime, timezone

import httpx
from sqlmodel import Session, select

from app.config import settings
from app.storage.db import engine
from app.storage.models import RawItem, ProcessingRun, ProcessingStatus

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def ingest_fmp_news() -> ProcessingRun:
    run = ProcessingRun(source="fmp_news", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    if not settings.FMP_API_KEY:
        run.status = "failed: FMP_API_KEY not set"
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        session.close()
        return run

    try:
        url = f"{FMP_BASE_URL}/stock_news?apikey={settings.FMP_API_KEY}&limit=100"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        articles = resp.json()

        for article in articles:
            title = article.get("title", "")
            link = article.get("url", "")
            text = article.get("text", "")
            symbol = article.get("symbol", "")
            published_at_str = article.get("publishedDate", "")

            raw_text = f"{title}\n\n{text}"
            content_hash = _make_hash(f"{link}:{raw_text}")

            existing = session.exec(
                select(RawItem).where(RawItem.hash == content_hash)
            ).first()
            if existing:
                run.items_skipped += 1
                continue

            published_at = _parse_date(published_at_str)

            item = RawItem(
                source="fmp_news",
                source_url=link,
                title=title[:500] if title else None,
                published_at=published_at,
                raw_text=raw_text[:10000],
                raw_json=article,
                hash=content_hash,
                ticker_candidates=symbol,
                processed_status=ProcessingStatus.pending,
            )
            session.add(item)
            run.items_fetched += 1

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


def ingest_fmp_insider() -> ProcessingRun:
    run = ProcessingRun(source="fmp_insider", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    if not settings.FMP_API_KEY:
        run.status = "failed: FMP_API_KEY not set"
        run.finished_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        session.close()
        return run

    try:
        url = f"{FMP_BASE_URL}/insider-trading?apikey={settings.FMP_API_KEY}&limit=100"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        trades = resp.json()

        for trade in trades:
            symbol = trade.get("symbol", "")
            acr = trade.get("acquirer", "")
            transaction_date = trade.get("transactionDate", "")
            transaction_type = trade.get("transactionType", "")
            shares = trade.get("securitiesTransacted", "")
            price = trade.get("transactionPrice", "")

            title = f"Insider {transaction_type}: {acr} - {symbol} - {shares} shares"
            raw_text = f"{title}\nSymbol: {symbol}\nAcquirer: {acr}\nDate: {transaction_date}\nType: {transaction_type}\nShares: {shares}\nPrice: {price}"
            content_hash = _make_hash(raw_text)

            existing = session.exec(
                select(RawItem).where(RawItem.hash == content_hash)
            ).first()
            if existing:
                run.items_skipped += 1
                continue

            item = RawItem(
                source="fmp_insider",
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}",
                title=title[:500],
                published_at=_parse_date(transaction_date),
                raw_text=raw_text,
                raw_json=trade,
                hash=content_hash,
                ticker_candidates=symbol,
                processed_status=ProcessingStatus.pending,
            )
            session.add(item)
            run.items_fetched += 1

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


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None