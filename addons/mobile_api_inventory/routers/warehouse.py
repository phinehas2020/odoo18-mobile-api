from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from odoo.api import Environment
from odoo.exceptions import AccessError, UserError
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.warehouse import (
    AdjustmentApplyRequest,
    AdjustmentReviewRequest,
    AdjustmentReviewResponse,
    ReturnApplyRequest,
    ReturnApplyResponse,
    ReturnReviewResponse,
    ScrapApplyRequest,
    ScrapReviewRequest,
    ScrapReviewResponse,
    StockLookupResponse,
)
from ..services.inventory_service import RecordVersionConflict
from ..services.warehouse_service import MobileWarehouseService

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _raise(exc):
    if isinstance(exc, RecordVersionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"server_version": exc.server_version, "message": str(exc), "conflict_type": "record_version"},
        )
    if isinstance(exc, AccessError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/stock", response_model=StockLookupResponse)
def stock(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    query: Optional[str] = Query(None),
    location_id: Optional[int] = Query(None),
    limit: int = Query(50),
):
    return StockLookupResponse(**MobileWarehouseService(env).stock(query, location_id, limit))


@router.post("/adjustments/review", response_model=AdjustmentReviewResponse)
def review_adjustment(payload: AdjustmentReviewRequest, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return AdjustmentReviewResponse(**MobileWarehouseService(env).review_adjustment(payload.quant_id, payload.counted_quantity))
    except (UserError, AccessError) as exc:
        _raise(exc)


@router.post("/adjustments/apply", response_model=AdjustmentReviewResponse)
def apply_adjustment(payload: AdjustmentApplyRequest, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return AdjustmentReviewResponse(**MobileWarehouseService(env).apply_adjustment(payload.dict()))
    except (UserError, AccessError) as exc:
        _raise(exc)


@router.post("/scraps/review", response_model=ScrapReviewResponse)
def review_scrap(payload: ScrapReviewRequest, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return ScrapReviewResponse(**MobileWarehouseService(env).review_scrap(payload.quant_id, payload.quantity, payload.picking_id))
    except (UserError, AccessError) as exc:
        _raise(exc)


@router.post("/scraps/apply", response_model=ScrapReviewResponse)
def apply_scrap(payload: ScrapApplyRequest, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return ScrapReviewResponse(**MobileWarehouseService(env).apply_scrap(payload.dict()))
    except (UserError, AccessError) as exc:
        _raise(exc)


@router.post("/pickings/{picking_id}/returns/review", response_model=ReturnReviewResponse)
def review_return(picking_id: int, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return ReturnReviewResponse(**MobileWarehouseService(env).review_return(picking_id))
    except (UserError, AccessError) as exc:
        _raise(exc)


@router.post("/pickings/{picking_id}/returns/apply", response_model=ReturnApplyResponse)
def apply_return(picking_id: int, payload: ReturnApplyRequest, env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)]):
    try:
        return ReturnApplyResponse(**MobileWarehouseService(env).apply_return(picking_id, payload.dict()))
    except (UserError, AccessError) as exc:
        _raise(exc)
