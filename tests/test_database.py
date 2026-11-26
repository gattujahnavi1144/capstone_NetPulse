import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select

import app.main as app_main
from app.db import database
from app.db.models import AlertRow, DeviceRow
from app.main import app
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository
from app.routes.alerts import router as alerts_router
from app.routes.devices import router as devices_router
from app.services.device_service import DeviceService


@pytest.fixture
def startup_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    try:
        yield engine
    finally:
        engine.dispose()


def test_application_database_is_isolated(tmp_path, sqlite_engine, session_factory) -> None:
    assert Path(sqlite_engine.url.database).is_relative_to(tmp_path)
    assert database.engine is sqlite_engine
    assert app_main.engine is sqlite_engine
    assert database.SessionLocal is session_factory


def test_session_commits_and_rolls_back(session_factory) -> None:

    dependency = database.get_session()
    session = next(dependency)
    session.add(DeviceRow(
        device_id="RTR-101", name="Router", device_type="router",
        ip_address="192.0.2.10", status="online"
    ))
    with pytest.raises(StopIteration):
        next(dependency)

    dependency = database.get_session()
    session = next(dependency)
    session.add(AlertRow(device_id="RTR-101", message="Offline"))
    with pytest.raises(ValueError):
        dependency.throw(ValueError("request failed"))

    with session_factory() as session:
        assert session.get(DeviceRow, "RTR-101") is not None
        assert session.scalars(select(AlertRow)).all() == []


def test_session_rolls_back_and_closes_when_commit_fails(monkeypatch) -> None:
    session = Mock()
    session.commit.side_effect = RuntimeError("commit failed")
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    dependency = database.get_session()
    assert next(dependency) is session
    with pytest.raises(RuntimeError, match="commit failed"):
        next(dependency)
    session.rollback.assert_called_once()
    session.close.assert_called_once()


def test_offline_transition_and_alert_roll_back_together(session_factory) -> None:
    session_scope = contextmanager(database.get_session)

    with session_scope() as session:
        session.add(DeviceRow(
            device_id="RTR-101", name="Router", device_type="router",
            ip_address="192.0.2.10", status="online"
        ))

    with pytest.raises(RuntimeError, match="after staging"):
        with session_scope() as session:
            repository = SQLAlchemyDeviceRepository(session)
            service = DeviceService(repository)
            assert service.update_status("RTR-101", "offline").status == "offline"
            assert session.get(DeviceRow, "RTR-101").status == "offline"
            alerts = session.scalars(select(AlertRow)).all()
            assert len(alerts) == 1
            assert alerts[0].device_id == "RTR-101"
            raise RuntimeError("after staging")

    with session_factory() as session:
        assert session.get(DeviceRow, "RTR-101").status == "online"
        assert session.scalars(select(AlertRow)).all() == []


def test_alert_timestamp_round_trips_as_utc(session_factory) -> None:
    timestamp = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    with session_factory() as session:
        session.add(AlertRow(device_id="RTR-101", message="Offline", timestamp=timestamp))
        session.commit()
    with session_factory() as session:
        alert = session.scalars(select(AlertRow)).one()
        assert alert.timestamp == timestamp


def test_startup_creates_tables(startup_engine, monkeypatch) -> None:
    monkeypatch.setattr("app.main.engine", startup_engine)

    async def start_app() -> None:
        async with app.router.lifespan_context(app):
            assert set(database.Base.metadata.tables) == {"devices", "alerts"}
            with startup_engine.connect() as connection:
                assert connection.dialect.has_table(connection, "devices")
                assert connection.dialect.has_table(connection, "alerts")

    asyncio.run(start_app())


def test_database_route_dependencies_are_function_scoped() -> None:
    def session_dependencies(dependant):
        for dependency in dependant.dependencies:
            if dependency.call is database.get_session:
                yield dependency
            yield from session_dependencies(dependency)

    for router in (devices_router, alerts_router):
        for route in router.routes:
            if isinstance(route, APIRoute):
                dependencies = list(session_dependencies(route.dependant))
                assert len(dependencies) == 1
                assert dependencies[0].scope == "function"


def test_request_commits_before_response_starts(monkeypatch) -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = []
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    response_statuses = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            session.commit.assert_called_once()
            session.close.assert_called_once()
            response_statuses.append(message["status"])

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/devices",
        "raw_path": b"/devices",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    assert response_statuses == [200]