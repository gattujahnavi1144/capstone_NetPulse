import asyncio
import json
import logging
import re

import pytest
from starlette.requests import Request
from structlog.contextvars import bind_contextvars, get_contextvars

from app.main import app, request_id_middleware
from app.repositories.sqlalchemy_device_repository import SQLAlchemyDeviceRepository


async def make_request(
    path: str, request_id: str | None = None, expected_error=None, *, method="GET", data=None,
    query_string=b"",
):
    headers = [(b"content-type", b"application/json")]
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    messages = []
    response_complete = asyncio.Event()
    received = False
    body = json.dumps(data).encode() if data is not None else b""

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await response_complete.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            response_complete.set()

    try:
        await app(scope, receive, send)
    except Exception as error:
        if expected_error is None or not isinstance(error, expected_error):
            raise
    else:
        assert expected_error is None
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_headers = dict(start["headers"])
    return start["status"], response_headers[b"x-request-id"].decode()


def test_request_ids_are_validated_and_correlate_device_logs(monkeypatch, caplog) -> None:
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [caplog.handler])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)

    async def run():
        async with app.router.lifespan_context(app):
            return await asyncio.gather(
                make_request("/devices/RTR-404", "valid_ID-123"),
                make_request("/devices/RTR-404", "A" * 64),
                make_request("/devices/RTR-404"),
                make_request("/devices/RTR-404", "token=secret"),
                make_request("/devices/RTR-404", "A" * 65),
                make_request("/devices/RTR-404", ""),
                make_request("/devices/RTR-404", "café"),
            )

    responses = asyncio.run(run())
    assert all(status == 404 for status, _ in responses)
    ids = [request_id for _, request_id in responses]
    assert ids[:2] == ["valid_ID-123", "A" * 64]
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in ids[2:])
    assert len(set(ids)) == len(ids)
    events = [json.loads(record.getMessage()) for record in caplog.records if record.levelno == logging.WARNING]
    assert len(events) == len(ids)
    assert {event["request_id"] for event in events} == set(ids)
    assert all(event["event"] == "device_error" for event in events)
    assert "token=secret" not in caplog.text


def test_unhandled_error_response_keeps_request_id(monkeypatch) -> None:
    def fail(_repository, _device_id):
        raise RuntimeError("failure")

    monkeypatch.setattr(SQLAlchemyDeviceRepository, "get_device", fail)

    async def run():
        async with app.router.lifespan_context(app):
            return await make_request("/devices/RTR-404", "request-1", RuntimeError)

    assert asyncio.run(run()) == (500, "request-1")


def test_request_completion_and_safe_error_logs(monkeypatch, caplog) -> None:
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [caplog.handler])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    device = {
        "device_id": "RTR-101",
        "name": "private-device-name",
        "device_type": "router",
        "ip_address": "192.0.2.10",
    }

    def fail(_repository, _device_id):
        raise RuntimeError("password=supersecret postgresql://user:secret@host/db")

    async def run():
        async with app.router.lifespan_context(app):
            assert await make_request("/health", "health-1", query_string=b"token=querysecret") == (200, "health-1")
            assert await make_request("/unmatched/path", "missing-route") == (404, "missing-route")
            assert await make_request("/unmatched/token=pathsecret", "sensitive-route") == (404, "sensitive-route")
            assert await make_request("/devices/token=secret", "missing-device") == (404, "missing-device")
            assert await make_request("/devices", "created", method="POST", data=device) == (201, "created")
            assert await make_request("/devices", "duplicate", method="POST", data=device) == (409, "duplicate")
            with monkeypatch.context() as patch:
                patch.setattr(SQLAlchemyDeviceRepository, "get_device", fail)
                assert await make_request("/devices/RTR-101", "failed", RuntimeError) == (500, "failed")

    asyncio.run(run())
    events = [json.loads(record.getMessage()) for record in caplog.records]
    completed = [event for event in events if event["event"] == "request_completed"]
    assert {event["request_id"] for event in completed} == {
        "health-1", "missing-route", "sensitive-route", "missing-device", "created", "duplicate", "failed"
    }
    assert len(completed) == 7
    by_id = {event["request_id"]: event for event in completed}
    assert (by_id["health-1"]["method"], by_id["health-1"]["path"], by_id["health-1"]["status_code"]) == ("GET", "/health", 200)
    assert by_id["missing-route"]["path"] == "/unmatched/path"
    assert by_id["sensitive-route"]["path"] == "/unmatched/[redacted]"
    assert (by_id["missing-device"]["path"], by_id["missing-device"]["status_code"]) == ("/devices/{device_id}", 404)
    assert (by_id["duplicate"]["method"], by_id["duplicate"]["status_code"]) == ("POST", 409)
    assert (by_id["failed"]["path"], by_id["failed"]["status_code"]) == ("/devices/{device_id}", 500)
    assert all(isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] >= 0 for event in completed)

    warnings = [event for event in events if event["level"] == "warning"]
    assert [(event["request_id"], event["error_type"], event["device_id"]) for event in warnings] == [
        ("missing-device", "DeviceNotFoundError", "[redacted]"),
        ("duplicate", "DeviceAlreadyExistsError", "RTR-101"),
    ]
    errors = [event for event in events if event["level"] == "error"]
    assert len(errors) == 1
    assert (errors[0]["event"], errors[0]["request_id"], errors[0]["error_type"]) == ("request_failed", "failed", "RuntimeError")
    assert "Traceback" in errors[0]["exception"] and "in fail" in errors[0]["exception"]
    assert all(record.exc_info is None for record in caplog.records)
    for secret in ("querysecret", "pathsecret", "token=secret", "private-device-name", "supersecret", "postgresql://"):
        assert secret not in caplog.text


def test_device_workflow_events_share_request_ids(monkeypatch, caplog) -> None:
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [caplog.handler])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    device = {
        "device_id": "RTR-101",
        "name": "secret device name",
        "device_type": "router",
        "ip_address": "192.0.2.10",
    }

    def fail_alert(_repository, _alert):
        raise RuntimeError("alert persistence failed")

    async def run():
        async with app.router.lifespan_context(app):
            assert await make_request("/devices", "register-1", method="POST", data=device) == (201, "register-1")
            assert await make_request("/devices", "duplicate-1", method="POST", data=device) == (409, "duplicate-1")
            assert await make_request("/devices/RTR-101/status", "offline-1", method="PATCH", data={"status": "offline"}) == (200, "offline-1")
            assert await make_request("/devices/RTR-101/status", "unchanged-1", method="PATCH", data={"status": "offline"}) == (200, "unchanged-1")
            assert await make_request("/devices/RTR-101/status", "online-1", method="PATCH", data={"status": "online"}) == (200, "online-1")
            with monkeypatch.context() as patch:
                patch.setattr(SQLAlchemyDeviceRepository, "save_alert", fail_alert)
                assert await make_request("/devices/RTR-101/status", "failed-1", RuntimeError, method="PATCH", data={"status": "offline"}) == (500, "failed-1")
            unsafe_device = {**device, "device_id": "token=secret"}
            assert await make_request("/devices", "register-2", method="POST", data=unsafe_device) == (201, "register-2")
            assert await make_request("/devices/token=secret/status", "offline-2", method="PATCH", data={"status": "offline"}) == (200, "offline-2")

    asyncio.run(run())
    events = [
        event for record in caplog.records
        if (event := json.loads(record.getMessage()))["event"] not in {"request_completed", "request_failed", "device_error"}
    ]
    assert [(event["request_id"], event["event"], event["device_id"]) for event in events] == [
        ("register-1", "device_registration_requested", "RTR-101"),
        ("register-1", "device_registered", "RTR-101"),
        ("duplicate-1", "device_registration_requested", "RTR-101"),
        ("offline-1", "device_status_changed", "RTR-101"),
        ("offline-1", "offline_alert_created", "RTR-101"),
        ("online-1", "device_status_changed", "RTR-101"),
        ("register-2", "device_registration_requested", "[redacted]"),
        ("register-2", "device_registered", "[redacted]"),
        ("offline-2", "device_status_changed", "[redacted]"),
        ("offline-2", "offline_alert_created", "[redacted]"),
    ]
    assert all(event["level"] == "info" for event in events)
    assert "secret device name" not in caplog.text
    assert "token=secret" not in caplog.text


def test_request_context_is_cleared_after_exception() -> None:
    async def run():
        bind_contextvars(stale="value")
        request = Request({
            "type": "http", "method": "GET", "path": "/test", "query_string": b"",
            "headers": [(b"x-request-id", b"request-1")],
        })

        async def fail(_request):
            assert get_contextvars() == {"request_id": "request-1"}
            raise RuntimeError("failure")

        with pytest.raises(RuntimeError, match="failure"):
            await request_id_middleware(request, fail)
        assert get_contextvars() == {}

    asyncio.run(run())