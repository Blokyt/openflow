import os
import tempfile
import pytest
from sqlalchemy import inspect


def test_create_database():
    from backend.core.database import create_engine_from_path, create_system_tables
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        assert os.path.exists(db_path)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "_config" in tables
        assert "_modules" in tables
        assert "_dashboard" in tables
        engine.dispose()


def test_get_session():
    from backend.core.database import create_engine_from_path, create_system_tables, get_session_factory
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as session:
            assert session is not None
        engine.dispose()


def test_register_module_in_db():
    from backend.core.database import (
        create_engine_from_path, create_system_tables,
        get_session_factory, register_module, get_module_version,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)
        register_module(SessionLocal, "transactions", "1.0.0")
        version = get_module_version(SessionLocal, "transactions")
        assert version == "1.0.0"
        engine.dispose()


def test_get_module_version_not_installed():
    from backend.core.database import (
        create_engine_from_path, create_system_tables,
        get_session_factory, get_module_version,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        engine = create_engine_from_path(db_path)
        create_system_tables(engine)
        SessionLocal = get_session_factory(engine)
        version = get_module_version(SessionLocal, "nonexistent")
        assert version is None
        engine.dispose()
