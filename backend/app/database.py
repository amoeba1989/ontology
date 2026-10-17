from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings
from app.db_engine import create_platform_engine

engine = create_platform_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
