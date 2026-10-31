import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from apps.api.deps import DbSession
from infrastructure.database.session import ping

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: DbSession) -> JSONResponse:
    """Readiness: the database answers."""
    try:
        ping(db)
    except SQLAlchemyError:
        logger.warning("database not ready", extra={"event": "ready_check_failed"})
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
    return JSONResponse(content={"status": "ok", "database": "up"})
