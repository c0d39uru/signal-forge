from sqlmodel import Session, create_engine
from app.config import settings

engine = create_engine(settings.DATABASE_URL)


def get_session():
    with Session(engine) as session:
        yield session


def init_db():
    from app.storage.models import SQLModel

    SQLModel.metadata.create_all(engine)