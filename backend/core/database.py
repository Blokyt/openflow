from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.core.models import SystemBase, ModuleRecord


def create_engine_from_path(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def create_system_tables(engine):
    SystemBase.metadata.create_all(engine)


def get_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine)


def register_module(session_factory: sessionmaker, module_id: str, version: str) -> None:
    with session_factory() as session:
        existing = session.query(ModuleRecord).filter_by(id=module_id).first()
        if existing:
            existing.version = version
        else:
            session.add(ModuleRecord(id=module_id, version=version, active=True))
        session.commit()


def get_module_version(session_factory: sessionmaker, module_id: str) -> str | None:
    with session_factory() as session:
        record = session.query(ModuleRecord).filter_by(id=module_id).first()
        return record.version if record else None
