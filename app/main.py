from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.routes.alerts import router as alerts_router
from app.routes.devices import router as devices_router
from app.routes.health import router as health_router
from app.services.device_service import DeviceAlreadyExistsError, DeviceNotFoundError


app = FastAPI(title="NetPulse API")


@app.exception_handler(DeviceAlreadyExistsError)
async def device_already_exists_handler(
	request: Request, error: DeviceAlreadyExistsError
) -> JSONResponse:
	return JSONResponse(
		status_code=status.HTTP_409_CONFLICT,
		content={"detail": str(error)},
	)


@app.exception_handler(DeviceNotFoundError)
async def device_not_found_handler(
	request: Request, error: DeviceNotFoundError
) -> JSONResponse:
	return JSONResponse(
		status_code=status.HTTP_404_NOT_FOUND,
		content={"detail": str(error)},
	)


app.include_router(devices_router)
app.include_router(alerts_router)
app.include_router(health_router)