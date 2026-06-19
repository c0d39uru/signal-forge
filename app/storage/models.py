from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, func
from sqlalchemy import Text
from sqlalchemy import JSON


class EventType(str, Enum):
    earnings_result = "earnings_result"
    earnings_guidance = "earnings_guidance"
    government_contract = "government_contract"
    large_customer_contract = "large_customer_contract"
    merger_acquisition = "merger_acquisition"
    fda_approval = "fda_approval"
    fda_rejection = "fda_rejection"
    ceo_change = "ceo_change"
    cfo_change = "cfo_change"
    layoffs = "layoffs"
    bankruptcy = "bankruptcy"
    lawsuit = "lawsuit"
    analyst_upgrade = "analyst_upgrade"
    analyst_downgrade = "analyst_downgrade"
    insider_buying = "insider_buying"
    insider_selling = "insider_selling"
    share_buyback = "share_buyback"
    offering_dilution = "offering_dilution"
    partnership = "partnership"
    product_launch = "product_launch"
    unknown = "unknown"


class ProcessingStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class Source(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    source_type: str
    base_url: str | None = None
    config_json: dict | None = Field(default=None, sa_column=Column(JSON))
    is_active: bool = True
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class RawItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_id: int | None = Field(default=None, foreign_key="source.id")
    source: str = Field(index=True)
    source_url: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )
    raw_text: str | None = Field(default=None, sa_column=Column(Text))
    raw_json: dict | None = Field(default=None, sa_column=Column(JSON))
    hash: str | None = Field(default=None, index=True)
    ticker_candidates: str | None = None
    processed_status: ProcessingStatus = Field(default=ProcessingStatus.pending, index=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class Company(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class Ticker(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, unique=True)
    company_id: int | None = Field(default=None, foreign_key="company.id")
    exchange: str | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    raw_item_id: int | None = Field(default=None, foreign_key="rawitem.id")
    ticker: str = Field(index=True)
    event_type: EventType
    summary: str | None = Field(default=None, sa_column=Column(Text))
    extracted_facts_json: dict | None = Field(default=None, sa_column=Column(JSON))
    sentiment_score: float | None = None
    confidence_score: float | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class EventScore(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id")
    impact_score: float = 0.0
    urgency_score: float = 0.0
    novelty_score: float = 0.0
    confidence_score: float = 0.0
    liquidity_score: float = 0.0
    final_score: float = 0.0
    reasoning: str | None = Field(default=None, sa_column=Column(Text))


class RedditMention(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    subreddit: str
    mention_count: int = 0
    sentiment_estimate: float | None = None
    mention_velocity: float | None = None
    fetched_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )


class ProcessingRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source: str
    items_fetched: int = 0
    items_processed: int = 0
    items_skipped: int = 0
    status: str = "running"
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime, server_default=func.now())
    )
    finished_at: datetime | None = None