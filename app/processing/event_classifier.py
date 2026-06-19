import json
import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app.config import settings
from app.storage.db import engine
from app.storage.models import (
    Event,
    EventType,
    RawItem,
    ProcessingStatus,
)

logger = logging.getLogger(__name__)


class AIExtractionResult(BaseModel):
    ticker: str = ""
    company_name: str = ""
    event_type: str = Field(default="unknown")
    summary: str = ""
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    extracted_facts: dict = Field(default_factory=dict)


class MockAIProvider:
    def extract(self, text: str, ticker_hint: str = "") -> AIExtractionResult:
        return AIExtractionResult(
            ticker=ticker_hint or "UNKNOWN",
            company_name="Mock Company",
            event_type="unknown",
            summary=text[:200] if text else "No content",
            sentiment_score=0.0,
            confidence_score=0.5,
            extracted_facts={},
        )


class OpenAIProvider:
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def extract(self, text: str, ticker_hint: str = "") -> AIExtractionResult:
        prompt = _build_prompt(text, ticker_hint)
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return AIExtractionResult(**data)


class OllamaProvider:
    def __init__(self):
        import httpx

        self.base_url = settings.OLLAMA_BASE_URL
        self.client = httpx.Client(timeout=60)

    def extract(self, text: str, ticker_hint: str = "") -> AIExtractionResult:
        prompt = _build_prompt(text, ticker_hint)
        resp = self.client.post(
            f"{self.base_url}/api/generate",
            json={"model": "llama3.2", "prompt": prompt, "stream": False, "format": "json"},
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["response"])
        return AIExtractionResult(**data)


def _build_prompt(text: str, ticker_hint: str = "") -> str:
    ticker_line = f"Ticker hint: {ticker_hint}\n" if ticker_hint else ""
    return f"""{ticker_line}Analyze this financial news and extract structured data.

News text:
{text[:3000]}

Respond ONLY with JSON matching this exact schema:
{{
  "ticker": "stock symbol, e.g. AAPL",
  "company_name": "full company name",
  "event_type": "one of: earnings_result, earnings_guidance, government_contract, large_customer_contract, merger_acquisition, fda_approval, fda_rejection, ceo_change, cfo_change, layoffs, bankruptcy, lawsuit, analyst_upgrade, analyst_downgrade, insider_buying, insider_selling, share_buyback, offering_dilution, partnership, product_launch, unknown",
  "summary": "one-sentence summary of the key event",
  "sentiment_score": 0.0,
  "confidence_score": 0.0,
  "extracted_facts": {{}}
}}

sentiment_score: -1.0 (very bearish) to 1.0 (very bullish)
confidence_score: 0.0 (uncertain) to 1.0 (very confident)
extracted_facts: key-value pairs of important facts (contract values, names, dates, etc.)"""


def get_provider() -> MockAIProvider | OpenAIProvider | OllamaProvider:
    provider = settings.AI_PROVIDER.lower()
    if provider == "openai":
        return OpenAIProvider()
    elif provider == "ollama":
        return OllamaProvider()
    return MockAIProvider()


def classify_item(raw_item: RawItem, provider=None) -> Event | None:
    if provider is None:
        provider = get_provider()

    text = raw_item.raw_text or ""
    ticker_hint = raw_item.ticker_candidates or ""

    try:
        result = provider.extract(text, ticker_hint)
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"AI extraction failed for item {raw_item.id}: {e}")
        return None

    try:
        event_type = EventType(result.event_type)
    except ValueError:
        event_type = EventType.unknown

    event = Event(
        raw_item_id=raw_item.id,
        ticker=result.ticker,
        event_type=event_type,
        summary=result.summary,
        extracted_facts_json=result.extracted_facts,
        sentiment_score=result.sentiment_score,
        confidence_score=result.confidence_score,
    )
    return event


def process_pending_items(limit: int = 100) -> list[Event]:
    session = Session(engine)
    provider = get_provider()

    items = session.exec(
        select(RawItem)
        .where(RawItem.processed_status == ProcessingStatus.pending)
        .limit(limit)
    ).all()

    events = []
    for item in items:
        item.processed_status = ProcessingStatus.processing
        session.add(item)
        session.commit()

        event = classify_item(item, provider)
        if event:
            session.add(event)
            session.commit()
            session.refresh(event)
            events.append(event)
            item.processed_status = ProcessingStatus.completed
        else:
            item.processed_status = ProcessingStatus.failed

        session.add(item)
        session.commit()

    session.close()
    return events