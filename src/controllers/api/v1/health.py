import logging

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
@inject
async def health(session: FromDishka[AsyncSession]) -> dict:
	"""Liveness/readiness probe.

	Returns 200 if Postgres is reachable (``SELECT 1``), otherwise 503. Used by the
	Dockerfile ``HEALTHCHECK`` and the Kubernetes liveness/readiness probes, so it
	must stay public (no JWT) and cheap.
	"""
	try:
		await session.execute(text("SELECT 1"))
	except Exception:
		logger.exception("Health check DB ping failed")
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="database unavailable",
		)
	return {"status": "ok"}
