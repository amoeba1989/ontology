from sqlalchemy.orm import sessionmaker, DeclarativeBase
from fastapi import Request
from sqlalchemy import event

from app.config import settings
from app.db_engine import create_platform_engine

engine = create_platform_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db(request: Request):
    db = SessionLocal()
    listener = None
    try:
        from app.services.scene_scope import SCOPED_PREFIXES, install_scene_scope
        path = request.url.path.removeprefix("/api/v1")
        scene_id = request.query_params.get("scene_id")
        if request.method == "GET" and scene_id and any(path == p or path.startswith(p + "/") for p in SCOPED_PREFIXES):
            listener = install_scene_scope(db, scene_id)
        yield db
    finally:
        if listener is not None:
            event.remove(db, "do_orm_execute", listener)
        db.close()
