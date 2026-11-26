import logging
import re
import traceback

import structlog


_SAFE_DEVICE_ID = re.compile(
    r"(?:[A-Z]{2,8}-[0-9]{1,10}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})"
)
_SENSITIVE_PATH_SEGMENT = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|credential", re.IGNORECASE
)
_SENSITIVE_FIELDS = {"password", "token", "api_key", "authorization", "secret"}


class SafeBoundLogger(structlog.stdlib.BoundLogger):
    def exception(self, event=None, *args, **kwargs):
        kwargs.setdefault("exc_info", True)
        return self._proxy_to_logger("error", event, *args, **kwargs)


def _safe_exception_trace(exc_info) -> str:
    return "Traceback (most recent call last):\n" + "".join(
        f'  File "{frame.f_code.co_filename}", line {line}, in {frame.f_code.co_name}\n'
        for frame, line in traceback.walk_tb(exc_info[2])
    )


def redact_sensitive_fields(logger, method_name, event_dict):
    for key in event_dict:
        if isinstance(key, str) and key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "***"
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.ExceptionRenderer(_safe_exception_trace),
            redact_sensitive_fields,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=SafeBoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


def safe_device_id(device_id: str) -> str:
    return device_id if _SAFE_DEVICE_ID.fullmatch(device_id) else "[redacted]"


def safe_unmatched_path(path: str) -> str:
    parts = path.split("/")
    redact_next = False
    for index, part in enumerate(parts):
        sensitive = bool(_SENSITIVE_PATH_SEGMENT.search(part))
        if redact_next or sensitive or any(char in part for char in "=@:"):
            parts[index] = "[redacted]"
        redact_next = sensitive and "=" not in part
    return "/".join(parts)