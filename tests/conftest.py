import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as app_main
from app.db import database


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    database.Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine):
    return sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def isolate_application_database(monkeypatch, sqlite_engine, session_factory):
    monkeypatch.setattr(database, "engine", sqlite_engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(app_main, "engine", sqlite_engine)