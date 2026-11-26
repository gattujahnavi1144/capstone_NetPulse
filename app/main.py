from contextlib import asynccontextmanager
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.db import models as db_models
from app.db.database import engine
from app.logging_config import configure_logging, safe_device_id, safe_unmatched_path
from app.routes.alerts import router as alerts_router
from app.routes.devices import router as devices_router
from app.routes.health import router as health_router
from app.services.device_service import DeviceAlreadyExistsError, DeviceNotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI):
	configure_logging()
	db_models.Base.metadata.create_all(bind=engine)
	yield


app = FastAPI(title="NetPulse API", lifespan=lifespan)
logger = structlog.get_logger(__name__)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
	clear_contextvars()
	started = time.perf_counter()
	request_id = request.headers.get("X-Request-ID", "")
	if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
		request_id = uuid4().hex
	request.state.request_id = request_id
	bind_contextvars(request_id=request_id)
	status_code = 500
	try:
		response = await call_next(request)
		status_code = response.status_code
		response.headers["X-Request-ID"] = request_id
		return response
	except Exception as error:
		logger.exception("request_failed", error_type=type(error).__name__)
		raise
	finally:
		try:
			route = request.scope.get("route")
			logger.info(
				"request_completed",
				method=request.method,
				path=getattr(route, "path", None) or safe_unmatched_path(request.url.path),
				status_code=status_code,
				duration_ms=round((time.perf_counter() - started) * 1000, 3),
			)
		finally:
			clear_contextvars()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, error: Exception) -> PlainTextResponse:
	request_id = getattr(request.state, "request_id", None)
	headers = {"X-Request-ID": request_id} if request_id else None
	return PlainTextResponse("Internal Server Error", status_code=500, headers=headers)


@app.exception_handler(DeviceAlreadyExistsError)
async def device_already_exists_handler(
	request: Request, error: DeviceAlreadyExistsError
) -> JSONResponse:
	logger.warning(
		"device_error", error_type=type(error).__name__,
		device_id=safe_device_id(error.device_id or ""),
	)
	return JSONResponse(
		status_code=status.HTTP_409_CONFLICT,
		content={"detail": str(error)},
	)


@app.exception_handler(DeviceNotFoundError)
async def device_not_found_handler(
	request: Request, error: DeviceNotFoundError
) -> JSONResponse:
	logger.warning(
		"device_error", error_type=type(error).__name__,
		device_id=safe_device_id(error.device_id or ""),
	)
	return JSONResponse(
		status_code=status.HTTP_404_NOT_FOUND,
		content={"detail": str(error)},
	)


app.include_router(devices_router)
app.include_router(alerts_router)
app.include_router(health_router)