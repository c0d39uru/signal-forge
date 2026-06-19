import re
from sqlmodel import Session, select

from app.storage.db import engine
from app.storage.models import Ticker, Company

TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")
COMMON_WORDS = {
    "THE", "AND", "FOR", "INC", "CORP", "LTD", "LLC", "CEO", "CFO",
    "CTO", "COO", "NYSE", "NASDAQ", "NYSE", "SEC", "FDA", "CEO",
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "AN", "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT", "ME",
    "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
}

EXTRA_NOISE = {
    "NEW", "SAY", "SAYS", "WILL", "HAS", "HAD", "NOT", "BUT", "ARE",
    "WAS", "WERE", "BEEN", "BEING", "HAVE", "HAVING", "DOES", "DOING",
    "FROM", "WITH", "THIS", "THAT", "THESE", "THOSE", "WHICH", "WHAT",
    "WHEN", "WHERE", "WHO", "HOW", "ALL", "EACH", "EVERY", "BOTH",
    "FEW", "MORE", "MOST", "OTHER", "SOME", "SUCH", "THAN", "TOO",
    "VERY", "CAN", "WILL", "JUST", "SHOULD", "NOW", "ALSO", "OVER",
    "STOCK", "SHARE", "MARKET", "TRADE", "PRICE",
}


def extract_tickers(text: str, known_tickers: set[str] | None = None) -> list[str]:
    candidates = set(TICKER_PATTERN.findall(text))
    candidates -= COMMON_WORDS
    candidates -= EXTRA_NOISE

    if known_tickers:
        return sorted(candidates & known_tickers)

    return sorted(c for c in candidates if len(c) >= 2)


def resolve_ticker(symbol: str, session: Session) -> Ticker | None:
    ticker = session.exec(select(Ticker).where(Ticker.symbol == symbol)).first()
    return ticker


def ensure_ticker(symbol: str, company_name: str | None = None, session: Session | None = None) -> Ticker:
    if session is None:
        session = Session(engine)

    existing = session.exec(select(Ticker).where(Ticker.symbol == symbol)).first()
    if existing:
        return existing

    company = Company(name=company_name or symbol)
    session.add(company)
    session.commit()
    session.refresh(company)

    ticker = Ticker(symbol=symbol, company_id=company.id)
    session.add(ticker)
    session.commit()
    session.refresh(ticker)

    return ticker