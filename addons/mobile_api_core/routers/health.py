from datetime import datetime, timezone

from fastapi import APIRouter

from odoo import release

from ..schemas.common import HealthResponse

router = APIRouter(tags=["core"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        server_time=datetime.now(timezone.utc),
        version=release.version,
    )
