import hashlib
import json
from datetime import datetime, timezone

import httpx
from sqlmodel import Session

from app.config import settings
from app.storage.db import engine
from app.storage.models import RawItem, ProcessingStatus, ProcessingRun


SEC_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_FILING_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_RECENT_URL = "https://www.sec.gov/cgi-bin/current?q1=0&q2=0&q3="

RSS_FEEDS_CONFIG = {
    "sec_edgar": {
        "base_url": "https://www.sec.gov/cgi-bin/browse-edgar",
        "rate_limit_delay": 0.1,
    }
}


def _make_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _sec_headers() -> dict:
    return {
        "User-Agent": settings.SEC_USER_AGENT,
        "Accept": "application/json",
    }


def ingest_8k_filings(days_back: int = 1) -> ProcessingRun:
    from time import sleep

    run = ProcessingRun(source="sec_8k", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        url = "https://efts.sec.gov/LATEST/search-index?q=%22Form+8-K%22&dateRange=custom&startdt={}&enddt={}&forms=8-K".format(
            _fmt_date(-days_back), _fmt_date(0)
        )
        resp = httpx.get(url, headers=_sec_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        filings = data.get("hits", {}).get("hits", [])

        for hit in filings:
            source_id = hit["_id"]
            filing = hit["_source"]
            title = filing.get("display_names", [""])[0] if filing.get("display_names") else ""
            filed_at = filing.get("file_date", "")
            link = f"https://www.sec.gov/Archives/edgar/data/{source_id}"

            raw_text = json.dumps(filing)
            content_hash = _make_hash(raw_text)

            existing = session.exec(
                RawItem.__table__.select().where(RawItem.hash == content_hash)
            ).first() if False else None

            if existing:
                run.items_skipped += 1
                continue

            item = RawItem(
                source="sec_8k",
                source_url=link,
                title=title[:500] if title else None,
                published_at=_parse_date(filed_at),
                raw_text=title,
                raw_json=filing,
                hash=content_hash,
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


def ingest_form4_filings(days_back: int = 1) -> ProcessingRun:
    run = ProcessingRun(source="sec_form4", status="running")
    session = Session(engine)
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        url = "https://efts.sec.gov/LATEST/search-index?q=%22Form+4%22&dateRange=custom&startdt={}&enddt={}&forms=3,4,5".format(
            _fmt_date(-days_back), _fmt_date(0)
        )
        resp = httpx.get(url, headers=_sec_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        filings = data.get("hits", {}).get("hits", [])

        for hit in filings:
            filing = hit["_source"]
            title = filing.get("display_names", [""])[0] if filing.get("display_names") else ""
            filed_at = filing.get("file_date", "")
            raw_text = json.dumps(filing)
            content_hash = _make_hash(raw_text)

            item = RawItem(
                source="sec_form4",
                source_url=f"https://www.sec.gov/Archives/edgar/data/{hit['_id']}",
                title=title[:500] if title else None,
                published_at=_parse_date(filed_at),
                raw_text=title,
                raw_json=filing,
                hash=content_hash,
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


def _fmt_date(offset_days: int) -> str:
    from datetime import timedelta

    d = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return d.strftime("%Y-%m-%d")


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None