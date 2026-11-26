from fastapi import APIRouter

from app.dependencies import RepositoryDep
from app.models import AlertResponse


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(repository: RepositoryDep) -> list[AlertResponse]:
    return repository.list_alerts()