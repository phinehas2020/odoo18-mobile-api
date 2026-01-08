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
    items = service.list_pickings(state_values, bool(mine), updated_since_dt)
    return [PickingListItem(**item) for item in items]


@router.get("/pickings/{picking_id}", response_model=PickingDetail)
def picking_detail(
    picking_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> PickingDetail:
    service = MobileInventoryService(env)
    detail = service.get_picking_detail(picking_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return PickingDetail(**detail)


@router.post("/pickings/{picking_id}/scan", response_model=ScanResponse)
def scan(
    picking_id: int,
    payload: ScanRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ScanResponse:
    service = MobileInventoryService(env)
    try:
        result = service.scan(
            picking_id,
            payload.dict(),
            device_id=payload.device_id,
            event_id=payload.event_id,
        )
    except RecordVersionConflict as conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "server_version": conflict.server_version,
                "message": "Record version conflict",
                "conflict_type": "record_version",
            },
        )
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
    try:
        result = service.validate(
            picking_id,
            payload.dict(),
            device_id=payload.device_id,
            event_id=payload.event_id,
        )
    except RecordVersionConflict as conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "server_version": conflict.server_version,
                "message": "Record version conflict",
                "conflict_type": "record_version",
            },
        )
    except UserError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return ValidateResponse(status=result.get("status"))
