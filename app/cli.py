from datetime import timedelta, datetime, timezone

import click

from app.storage.db import init_db


@click.group()
def cli():
    """Market News Scanner CLI"""
    pass


@cli.command()
@click.option("--source", type=click.Choice(["sec", "rss", "fmp", "reddit"]), required=True)
@click.option("--days-back", default=1, help="Days to look back for filings")
def ingest(source: str, days_back: int):
    """Ingest news from a data source."""
    init_db()

    if source == "sec":
        from app.ingestion.sec_edgar import ingest_8k_filings, ingest_form4_filings

        click.echo(f"Ingesting SEC 8-K filings (last {days_back} days)...")
        result_8k = ingest_8k_filings(days_back=days_back)
        click.echo(f"8-K: {result_8k.items_fetched} fetched, {result_8k.items_skipped} skipped, status={result_8k.status}")

        click.echo(f"Ingesting SEC Form 4 filings (last {days_back} days)...")
        result_4 = ingest_form4_filings(days_back=days_back)
        click.echo(f"Form 4: {result_4.items_fetched} fetched, {result_4.items_skipped} skipped, status={result_4.status}")

    elif source == "rss":
        from app.ingestion.rss import ingest_rss

        click.echo("Ingesting RSS feeds...")
        result = ingest_rss()
        click.echo(f"RSS: {result.items_fetched} fetched, {result.items_skipped} skipped, status={result.status}")

    elif source == "fmp":
        from app.ingestion.fmp import ingest_fmp_news, ingest_fmp_insider

        click.echo("Ingesting FMP news...")
        result = ingest_fmp_news()
        click.echo(f"FMP News: {result.items_fetched} fetched, {result.items_skipped} skipped, status={result.status}")

        click.echo("Ingesting FMP insider trading...")
        result = ingest_fmp_insider()
        click.echo(f"FMP Insider: {result.items_fetched} fetched, {result.items_skipped} skipped, status={result.status}")

    elif source == "reddit":
        from app.ingestion.reddit import ingest_reddit

        click.echo("Ingesting Reddit mentions...")
        result = ingest_reddit()
        click.echo(f"Reddit: {result.items_fetched} fetched, {result.items_skipped} skipped, status={result.status}")


@cli.command()
@click.option("--limit", default=100, help="Max items to process")
def process(limit: int):
    """Process pending raw items into events with AI classification."""
    init_db()

    from app.processing.event_classifier import process_pending_items

    click.echo(f"Processing up to {limit} pending items...")
    events = process_pending_items(limit=limit)
    click.echo(f"Created {len(events)} events")

    from app.processing.scoring import score_event

    scored = 0
    for event in events:
        score = score_event(event)
        click.echo(f"  Event {event.id} ({event.ticker}/{event.event_type.value}): final_score={score.final_score:.3f}")
        scored += 1

    click.echo(f"Scored {scored} events")


@cli.command("top-events")
@click.option("--since", default="24h", help="Time window (e.g. 24h, 7d)")
@click.option("--min-score", default=0.7, type=float, help="Minimum final score")
def top_events(since: str, min_score: float):
    """Show top-scored events."""
    init_db()

    from app.api.main import _parse_since, _serialize_event, _serialize_score
    from sqlmodel import Session, select

    from app.storage.db import engine
    from app.storage.models import Event, EventScore

    since_dt = _parse_since(since)

    session = Session(engine)
    events = session.exec(
        select(Event).where(Event.created_at >= since_dt).order_by(Event.created_at.desc())
    ).all()

    results = []
    for event in events:
        score = session.exec(
            select(EventScore).where(EventScore.event_id == event.id)
        ).first()
        if score and score.final_score >= min_score:
            results.append((event, score))

    results.sort(key=lambda x: x[1].final_score, reverse=True)

    if not results:
        click.echo("No events found matching criteria.")
        session.close()
        return

    click.echo(f"{'ID':<6} {'Ticker':<8} {'Type':<22} {'Score':<8} {'Summary'}")
    click.echo("-" * 80)
    for event, score in results:
        click.echo(
            f"{event.id:<6} {event.ticker:<8} {event.event_type.value:<22} "
            f"{score.final_score:<8.3f} {(event.summary or '')[:40]}"
        )

    session.close()


@cli.command("show-event")
@click.argument("event_id", type=int)
def show_event(event_id: int):
    """Show details for a specific event."""
    init_db()

    from sqlmodel import Session, select

    from app.storage.db import engine
    from app.storage.models import Event, EventScore

    session = Session(engine)
    event = session.get(Event, event_id)
    if not event:
        click.echo(f"Event {event_id} not found.")
        session.close()
        return

    score = session.exec(
        select(EventScore).where(EventScore.event_id == event.id)
    ).first()

    click.echo(f"Event #{event.id}")
    click.echo(f"  Ticker: {event.ticker}")
    click.echo(f"  Type:   {event.event_type.value}")
    click.echo(f"  Summary: {event.summary}")
    click.echo(f"  Sentiment: {event.sentiment_score}")
    click.echo(f"  Confidence: {event.confidence_score}")
    click.echo(f"  Facts: {event.extracted_facts_json}")
    click.echo(f"  Created: {event.created_at}")

    if score:
        click.echo(f"\n  Score:")
        click.echo(f"    Impact:     {score.impact_score:.3f}")
        click.echo(f"    Urgency:    {score.urgency_score:.3f}")
        click.echo(f"    Novelty:    {score.novelty_score:.3f}")
        click.echo(f"    Confidence: {score.confidence_score:.3f}")
        click.echo(f"    Liquidity:  {score.liquidity_score:.3f}")
        click.echo(f"    Final:      {score.final_score:.3f}")
        click.echo(f"    Reasoning:  {score.reasoning}")

    session.close()


@cli.command()
def seed():
    """Seed database with mock data for demo purposes."""
    init_db()

    from sqlmodel import Session

    from app.storage.db import engine
    from app.storage.models import (
        Company,
        Event,
        EventScore,
        EventType,
        RawItem,
        ProcessingStatus,
        Ticker,
    )

    session = Session(engine)

    tickers_data = [
        ("AAPL", "Apple Inc."),
        ("NVDA", "NVIDIA Corporation"),
        ("TSLA", "Tesla, Inc."),
        ("MSFT", "Microsoft Corporation"),
        ("META", "Meta Platforms, Inc."),
    ]

    for symbol, name in tickers_data:
        existing = session.exec(select(Ticker).where(Ticker.symbol == symbol)).first()
        if existing:
            continue
        company = Company(name=name)
        session.add(company)
        session.commit()
        session.refresh(company)
        ticker = Ticker(symbol=symbol, company_id=company.id)
        session.add(ticker)
        session.commit()

    mock_items = [
        {
            "source": "mock",
            "title": "NVIDIA Wins $500M Defense Contract",
            "raw_text": "NVIDIA Corporation announced it has been awarded a $500 million contract from the Department of Defense for AI chip supplies.",
            "tickercandidates": "NVDA",
        },
        {
            "source": "mock",
            "title": "Apple CFO Luca Maestri Steps Down",
            "raw_text": "Apple Inc. announced that CFO Luca Maestri will transition to a new role, with Kedar Desai named as his successor.",
            "tickercandidates": "AAPL",
        },
        {
            "source": "mock",
            "title": "Tesla Receives FDA Approval for Neural Implant Trial",
            "raw_text": "Tesla's Neuralink division received FDA approval for its first human clinical trial of brain-computer interface technology.",
            "tickercandidates": "TSLA",
        },
        {
            "source": "mock",
            "title": "Microsoft Beats Q3 Earnings Estimates",
            "raw_text": "Microsoft reported Q3 earnings of $2.95 per share, beating analyst estimates of $2.78, driven by strong Azure cloud growth.",
            "tickercandidates": "MSFT",
        },
        {
            "source": "mock",
            "title": "Meta Announces $10B Share Buyback Program",
            "raw_text": "Meta Platforms authorized a new $10 billion share repurchase program, signaling confidence in the company's financial outlook.",
            "tickercandidates": "META",
        },
    ]

    for item_data in mock_items:
        import hashlib

        raw = RawItem(
            source=item_data["source"],
            title=item_data["title"],
            raw_text=item_data["raw_text"],
            ticker_candidates=item_data["tickercandidates"],
            hash=hashlib.sha256(item_data["raw_text"].encode()).hexdigest(),
            processed_status=ProcessingStatus.completed,
        )
        session.add(raw)
        session.commit()
        session.refresh(raw)

    mock_events = [
        (1, "NVDA", EventType.government_contract, "NVIDIA won a $500M defense contract.", 0.85, 0.9),
        (2, "AAPL", EventType.cfo_change, "Apple CFO Luca Maestri stepping down.", -0.3, 0.85),
        (3, "TSLA", EventType.fda_approval, "Tesla Neuralink received FDA approval for human trials.", 0.9, 0.75),
        (4, "MSFT", EventType.earnings_result, "Microsoft beat Q3 earnings estimates with strong Azure growth.", 0.7, 0.95),
        (5, "META", EventType.share_buyback, "Meta announced a $10B share buyback program.", 0.6, 0.9),
    ]

    for raw_id, ticker, etype, summary, sentiment, confidence in mock_events:
        event = Event(
            raw_item_id=raw_id,
            ticker=ticker,
            event_type=etype,
            summary=summary,
            sentiment_score=sentiment,
            confidence_score=confidence,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        from app.processing.scoring import compute_score

        score = compute_score(event)
        score.event_id = event.id
        session.add(score)
        session.commit()

    click.echo("Seeded mock data successfully.")
    session.close()


if __name__ == "__main__":
    cli()