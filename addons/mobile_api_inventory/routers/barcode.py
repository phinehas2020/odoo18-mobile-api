import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.barcode import BarcodeResolveResponse
from ..services.inventory_service import MobileInventoryService

router = APIRouter(tags=["barcode"])
_logger = logging.getLogger(__name__)


@router.get("/barcode/resolve", response_model=BarcodeResolveResponse)
def resolve(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    code: str = Query(...),
) -> BarcodeResolveResponse:
    service = MobileInventoryService(env)
    _logger.info("mobile_api.barcode.resolve.route.start user_id=%s code_hash=%s", env.user.id, hash(code))
    resolved = service.resolve_barcode(code)
    if not resolved:
        _logger.warning("mobile_api.barcode.resolve.route.not_found user_id=%s code_hash=%s", env.user.id, hash(code))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _logger.info(
        "mobile_api.barcode.resolve.route.success user_id=%s match_type=%s id=%s",
        env.user.id,
        resolved.get("match_type"),
        resolved.get("id"),
    )
    return BarcodeResolveResponse(**resolved)
