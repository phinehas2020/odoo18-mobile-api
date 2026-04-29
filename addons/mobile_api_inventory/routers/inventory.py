import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo import fields
from odoo.api import Environment
from odoo.exceptions import UserError

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.inventory import (
    PickingDetail,
    PickingListItem,
    ScanRequest,
    ScanResponse,
    ValidateRequest,
    ValidateResponse,
)
from ..services.inventory_service import MobileInventoryService, RecordVersionConflict

router = APIRouter(prefix="/inventory", tags=["inventory"])
_logger = logging.getLogger(__name__)


@router.get("/pickings", response_model=List[PickingListItem])
def list_pickings(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    state: Optional[str] = Query(None),
    mine: Optional[int] = Query(0),
    updated_since: Optional[str] = Query(None),
) -> List[PickingListItem]:
    service = MobileInventoryService(env)
    state_values = [s.strip() for s in state.split(",")] if state else None
    updated_since_dt = (
        fields.Datetime.to_datetime(updated_since) if updated_since else None
    )
    _logger.info(
        "mobile_api.inventory.pickings.route.start user_id=%s state=%s mine=%s updated_since=%s",
        env.user.id,
        state_values,
        bool(mine),
        updated_since_dt,
    )
    items = service.list_pickings(state_values, bool(mine), updated_since_dt)
    _logger.info("mobile_api.inventory.pickings.route.success user_id=%s count=%s", env.user.id, len(items))
    return [PickingListItem(**item) for item in items]


@router.get("/pickings/{picking_id}", response_model=PickingDetail)
def picking_detail(
    picking_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> PickingDetail:
    service = MobileInventoryService(env)
    _logger.info("mobile_api.inventory.detail.route.start user_id=%s picking_id=%s", env.user.id, picking_id)
    detail = service.get_picking_detail(picking_id)
    if not detail:
        _logger.warning("mobile_api.inventory.detail.route.not_found user_id=%s picking_id=%s", env.user.id, picking_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _logger.info("mobile_api.inventory.detail.route.success user_id=%s picking_id=%s lines=%s", env.user.id, picking_id, len(detail.get("lines", [])))
    return PickingDetail(**detail)


@router.post("/pickings/{picking_id}/scan", response_model=ScanResponse)
def scan(
    picking_id: int,
    payload: ScanRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ScanResponse:
    service = MobileInventoryService(env)
    _logger.info("mobile_api.inventory.scan.route.start user_id=%s picking_id=%s device_id=%s event_id=%s", env.user.id, picking_id, payload.device_id, payload.event_id)
    try:
        result = service.scan(
            picking_id,
            payload.dict(),
            device_id=payload.device_id,
            event_id=payload.event_id,
        )
    except RecordVersionConflict as conflict:
        _logger.warning("mobile_api.inventory.scan.route.conflict user_id=%s picking_id=%s event_id=%s server_version=%s", env.user.id, picking_id, payload.event_id, conflict.server_version)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "server_version": conflict.server_version,
                "message": "Record version conflict",
                "conflict_type": "record_version",
            },
        )
    _logger.info("mobile_api.inventory.scan.route.success user_id=%s picking_id=%s event_id=%s status=%s lines=%s", env.user.id, picking_id, payload.event_id, result.get("status"), len(result.get("updated_lines", [])))
    return ScanResponse(
        status=result.get("status"),
        updated_lines=result.get("updated_lines", []),
        warnings=result.get("warnings", []),
        next_expected=result.get("next_expected"),
    )


@router.post("/pickings/{picking_id}/validate", response_model=ValidateResponse)
def validate(
    picking_id: int,
    payload: ValidateRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ValidateResponse:
    service = MobileInventoryService(env)
    _logger.info("mobile_api.inventory.validate.route.start user_id=%s picking_id=%s device_id=%s event_id=%s", env.user.id, picking_id, payload.device_id, payload.event_id)
    try:
        result = service.validate(
            picking_id,
            payload.dict(),
            device_id=payload.device_id,
            event_id=payload.event_id,
        )
    except RecordVersionConflict as conflict:
        _logger.warning("mobile_api.inventory.validate.route.conflict user_id=%s picking_id=%s event_id=%s server_version=%s", env.user.id, picking_id, payload.event_id, conflict.server_version)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "server_version": conflict.server_version,
                "message": "Record version conflict",
                "conflict_type": "record_version",
            },
        )
    except UserError as exc:
        _logger.warning("mobile_api.inventory.validate.route.user_error user_id=%s picking_id=%s event_id=%s message=%s", env.user.id, picking_id, payload.event_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    _logger.info("mobile_api.inventory.validate.route.success user_id=%s picking_id=%s event_id=%s status=%s", env.user.id, picking_id, payload.event_id, result.get("status"))
    return ValidateResponse(status=result.get("status"))
