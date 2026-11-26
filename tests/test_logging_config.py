import json
import logging
from datetime import datetime

import structlog

from app.logging_config import configure_logging, safe_device_id


def test_logging_configuration_is_idempotent_and_preserves_uvicorn(monkeypatch) -> None:
    app_logger = logging.getLogger("app")
    root_logger = logging.getLogger()
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_handlers = list(uvicorn_logger.handlers)
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    monkeypatch.setattr(root_logger, "handlers", [])

    configure_logging()
    configure_logging()

    assert app_logger.level == logging.INFO
    assert len(app_logger.handlers) == 1
    assert not app_logger.propagate
    assert uvicorn_logger.handlers == uvicorn_handlers
    assert root_logger.handlers == []


def test_logging_configuration_preserves_existing_root_handler(monkeypatch, capsys) -> None:
    app_logger = logging.getLogger("app")
    root_logger = logging.getLogger()
    root_handlers = list(root_logger.handlers)
    assert root_handlers
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)

    configure_logging()
    configure_logging()
    with structlog.contextvars.bound_contextvars(request_id="request-123"):
        structlog.get_logger("app.test").info("test_event", device_id="RTR-101")

    assert app_logger.level == logging.INFO
    assert len(app_logger.handlers) == 1
    assert root_logger.handlers == root_handlers
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "test_event"
    assert event["level"] == "info"
    assert event["device_id"] == "RTR-101"
    assert event["request_id"] == "request-123"
    assert datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


def test_safe_device_id_accepts_generated_uuid() -> None:
    device_id = "123e4567-e89b-12d3-a456-426614174000"
    assert safe_device_id(device_id) == device_id
    assert safe_device_id("RTR-101\nforged_event") == "[redacted]"


def test_sensitive_fields_are_redacted_in_json(monkeypatch, capsys) -> None:
    app_logger = logging.getLogger("app")
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", app_logger.propagate)
    configure_logging()

    with structlog.contextvars.bound_contextvars(SECRET="fake-context-secret"):
        structlog.get_logger("app.redaction_test").info(
            "redaction_test",
            token="DEMO-DO-NOT-USE",
            Password="fake-password",
            API_KEY="fake-api-key",
            Authorization="fake-authorization",
            device_id="RTRTEST",
            token_count=2,
        )

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    for key in ("token", "Password", "API_KEY", "Authorization", "SECRET"):
        assert event[key] == "***"
    assert event["device_id"] == "RTRTEST"
    assert event["token_count"] == 2
    assert "DEMO-DO-NOT-USE" not in lines[0]