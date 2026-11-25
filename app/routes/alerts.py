from fastapi import APIRouter

from app.dependencies import repository
from app.models import AlertResponse


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts() -> list[AlertResponse]:
    return repository.list_alerts()