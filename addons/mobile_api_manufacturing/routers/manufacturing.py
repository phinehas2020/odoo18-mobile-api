import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.manufacturing import ManufacturingOrderDetail, ManufacturingOrderItem
from ..services.manufacturing_service import MobileManufacturingService

router = APIRouter(prefix="/manufacturing", tags=["manufacturing"])
_logger = logging.getLogger(__name__)


@router.get("/orders", response_model=List[ManufacturingOrderItem])
def orders(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    attention: str = Query("due_or_late"),
    limit: int = Query(50, ge=1, le=200),
) -> List[ManufacturingOrderItem]:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.orders.route.start user_id=%s attention=%s limit=%s",
        env.user.id,
        attention,
        limit,
    )
    items = service.list_orders(attention=attention, limit=limit)
    _logger.info(
        "mobile_api.manufacturing.orders.route.success user_id=%s count=%s",
        env.user.id,
        len(items),
    )
    return [ManufacturingOrderItem(**item) for item in items]


@router.get("/orders/{order_id}", response_model=ManufacturingOrderDetail)
def order_detail(
    order_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.detail.route.start user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    detail = service.get_order(order_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _logger.info(
        "mobile_api.manufacturing.detail.route.success user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    return ManufacturingOrderDetail(**detail)

