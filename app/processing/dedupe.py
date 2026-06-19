import hashlib
from difflib import SequenceMatcher

from sqlmodel import Session, select

from app.storage.db import engine
from app.storage.models import RawItem


def is_duplicate(item: RawItem, session: Session) -> bool:
    if not item.source_url and not item.title and not item.hash:
        return False

    if item.hash:
        existing = session.exec(
            select(RawItem).where(RawItem.hash == item.hash)
        ).first()
        if existing and existing.id != item.id:
            return True

    if item.source_url:
        existing = session.exec(
            select(RawItem).where(RawItem.source_url == item.source_url)
        ).first()
        if existing and existing.id != item.id:
            return True

    if item.title:
        similar = session.exec(
            select(RawItem).where(RawItem.source == item.source)
        ).all()
        for existing in similar:
            if existing.id != item.id and existing.title:
                ratio = SequenceMatcher(None, item.title, existing.title).ratio()
                if ratio > 0.92:
                    return True

    return False


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def is_near_duplicate_content(text_a: str, text_b: str, threshold: float = 0.85) -> bool:
    ratio = SequenceMatcher(None, text_a[:5000], text_b[:5000]).ratio()
    return ratio > threshold