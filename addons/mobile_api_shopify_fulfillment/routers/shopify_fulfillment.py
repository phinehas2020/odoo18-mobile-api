import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, Query

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.shopify_fulfillment import ShopifyRecentOrderItem
from ..services.shopify_fulfillment_service import MobileShopifyFulfillmentService

router = APIRouter(prefix="/shopify", tags=["shopify"])
_logger = logging.getLogger(__name__)


@router.get("/orders/recent", response_model=List[ShopifyRecentOrderItem])
def recent_orders(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
) -> List[ShopifyRecentOrderItem]:
    service = MobileShopifyFulfillmentService(env)
    _logger.info(
        "mobile_api.shopify_fulfillment.recent_orders.route.start user_id=%s hours=%s limit=%s",
        env.user.id,
        hours,
        limit,
    )
    items = service.recent_orders(hours=hours, limit=limit)
    _logger.info(
        "mobile_api.shopify_fulfillment.recent_orders.route.success user_id=%s count=%s",
        env.user.id,
        len(items),
    )
    return [ShopifyRecentOrderItem(**item) for item in items]

