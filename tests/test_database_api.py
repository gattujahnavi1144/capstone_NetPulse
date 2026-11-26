import asyncio
import json
import logging
import re
import sys
from datetime import datetime

import pytest
import structlog
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import database
from app.db.models import AlertRow, DeviceRow
from app.main import app
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository


@pytest.fixture
def client(session_factory, isolate_application_database, monkeypatch, capfd):
    def override_get_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def unexpected_session():
        raise AssertionError("Application session factory must not be used by TestClient")

    monkeypatch.setattr(database, "SessionLocal", unexpected_session)
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    app.dependency_overrides[database.get_session] = override_get_session
    try:
        with TestClient(app) as test_client:
            monkeypatch.setattr(app_logger.handlers[0], "stream", sys.__stderr__)
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("supplied_id", [None, "client-ID_123", "bad token=secret"])
def test_client_request_ids_and_rendered_logs(client, capfd, supplied_id) -> None:
    headers = {"X-Request-ID": supplied_id} if supplied_id is not None else {}
    response = client.get("/devices/RTR-404?token=querysecret", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Device RTR-404 was not found"}
    request_id = response.headers["X-Request-ID"]
    if supplied_id == "client-ID_123":
        assert request_id == supplied_id
    else:
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)

    output = capfd.readouterr().err
    events = [json.loads(line) for line in output.splitlines()]
    assert [event["event"] for event in events] == ["device_error", "request_completed"]
    for event in events:
        assert event["request_id"] == request_id
        assert event["level"] in {"info", "warning"}
        assert datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    assert events[0]["device_id"] == "RTR-404"
    assert events[1]["path"] == "/devices/{device_id}"
    assert events[1]["status_code"] == 404
    assert "querysecret" not in output and "bad token=secret" not in output


def test_client_redaction_uses_rendered_json(client, capfd) -> None:
    structlog.get_logger("app.test").info(
        "redaction_test", token="DEMO-DO-NOT-USE", device_id="RTRTEST"
    )
    output = capfd.readouterr().err
    event = json.loads(output.strip())
    assert event["token"] == "***"
    assert event["device_id"] == "RTRTEST"
    assert "DEMO-DO-NOT-USE" not in output


def test_client_persists_one_alert_and_preserves_errors(client, session_factory) -> None:
    device = {
        "device_id": "RTR-101",
        "name": "Core Router",
        "device_type": "router",
        "ip_address": "192.0.2.10",
    }
    created = client.post("/devices", json=device)
    assert created.status_code == 201
    assert set(created.json()) == {"device_id", "name", "device_type", "ip_address", "status", "created_at"}
    assert created.json()["status"] == "online"
    duplicate = client.post("/devices", json=device)
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Device RTR-101 is already registered"}
    missing = client.get("/devices/RTR-404")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Device RTR-404 was not found"}

    for _ in range(2):
        response = client.patch("/devices/RTR-101/status", json={"status": "offline"})
        assert response.status_code == 200
        assert response.json()["status"] == "offline"
    alerts = client.get("/alerts").json()
    assert len(alerts) == 1
    assert set(alerts[0]) == {"device_id", "message", "timestamp"}
    assert alerts[0]["device_id"] == "RTR-101"
    assert alerts[0]["message"] == "Device RTR-101 went offline."
    with session_factory() as session:
        rows = session.scalars(select(AlertRow)).all()
        assert len(rows) == 1
        assert rows[0].device_id == "RTR-101"
        assert session.get(DeviceRow, "RTR-101").status == "offline"


def test_client_rolls_back_failed_alert(client, session_factory, monkeypatch) -> None:
    device = {
        "device_id": "RTR-101", "name": "Core Router", "device_type": "router",
        "ip_address": "192.0.2.10",
    }
    assert client.post("/devices", json=device).status_code == 201

    def fail_alert(_repository, _alert):
        raise RuntimeError("test alert failure")

    monkeypatch.setattr(SQLAlchemyDeviceRepository, "save_alert", fail_alert)
    with pytest.raises(RuntimeError, match="test alert failure"):
        client.patch("/devices/RTR-101/status", json={"status": "offline"})
    with session_factory() as session:
        assert session.get(DeviceRow, "RTR-101").status == "online"
        assert session.scalars(select(AlertRow)).all() == []


def test_database_api_workflow(session_factory, monkeypatch) -> None:
    sessions = []

    def create_session():
        session = session_factory()
        sessions.append(session)
        return session

    monkeypatch.setattr(database, "SessionLocal", create_session)

    async def request(method, path, data=None, expected_error=None):
        session_count = len(sessions)
        body = json.dumps(data).encode() if data is not None else b""
        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        try:
            await app(scope, receive, send)
        except Exception as error:
            if expected_error is None or not isinstance(error, expected_error):
                raise
        else:
            assert expected_error is None
        assert len(sessions) == session_count + 1
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        )
        return status, json.loads(response_body) if response_body.startswith((b"{", b"[")) else None

    async def workflow():
        async with app.router.lifespan_context(app):
            device = {
                "device_id": "RTR-101",
                "name": "Core Router",
                "device_type": "router",
                "ip_address": "192.0.2.10",
            }
            status, created = await request("POST", "/devices", device)
            assert status == 201
            assert created["status"] == "online"
            assert await request("POST", "/devices", device) == (409, {"detail": "Device RTR-101 is already registered"})
            assert await request("GET", "/devices/missing") == (404, {"detail": "Device missing was not found"})
            assert (await request("PATCH", "/devices/missing/status", {"status": "offline"}))[0] == 404
            assert (await request("POST", "/devices", {**device, "ip_address": "invalid"}))[0] == 422

            offline = {**device, "device_id": "SWT-101", "device_type": "switch", "status": "offline"}
            assert (await request("POST", "/devices", offline))[0] == 201
            assert (await request("GET", "/alerts"))[1] == []
            status, summary = await request("GET", "/devices/summary")
            assert status == 200
            assert summary == {"total_devices": 2, "online_count": 1, "offline_count": 1, "device_types": ["router", "switch"]}
            status, probe = await request("GET", "/devices/RTR-101/probe")
            assert status == 200
            assert probe == {"device_id": "RTR-101", "reachable": True, "simulated": True}

            def fail_alert(self, alert):
                raise RuntimeError("alert persistence failed")

            with monkeypatch.context() as patch:
                patch.setattr(SQLAlchemyDeviceRepository, "save_alert", fail_alert)
                status, _ = await request(
                    "PATCH", "/devices/RTR-101/status", {"status": "offline"}, RuntimeError
                )
                assert status == 500
            assert (await request("GET", "/devices/RTR-101"))[1]["status"] == "online"

            assert (await request("PATCH", "/devices/RTR-101/status", {"status": "offline"}))[0] == 200
            assert (await request("PATCH", "/devices/RTR-101/status", {"status": "offline"}))[0] == 200
            status, alerts = await request("GET", "/alerts")
            assert status == 200
            assert len(alerts) == 1
            assert alerts[0]["device_id"] == "RTR-101"
            assert alerts[0]["message"] == "Device RTR-101 went offline."
            assert alerts[0]["timestamp"].endswith("Z")

        async with app.router.lifespan_context(app):
            assert (await request("GET", "/devices/RTR-101"))[1]["status"] == "offline"
            assert len((await request("GET", "/alerts"))[1]) == 1
            assert (await request("GET", "/devices/summary"))[1] == {
                "total_devices": 2,
                "online_count": 0,
                "offline_count": 2,
                "device_types": ["router", "switch"],
            }

    asyncio.run(workflow())