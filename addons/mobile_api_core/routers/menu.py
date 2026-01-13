import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.menu import MenuItem, MenuResponse

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])


@router.get("/menu", response_model=MenuResponse)
def menu(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> MenuResponse:
    user = env.user
    items = []

    _logger.info(
        "Menu request - User: %s (id=%s), groups: %s",
        user.login,
        user.id,
        [g.full_name for g in user.groups_id],
    )

    # Admin users get all modules
    is_admin = user.has_group("base.group_system") or user._is_superuser

    has_stock = is_admin or user.has_group("stock.group_stock_user")
    has_sales = is_admin or user.has_group("sales_team.group_sale_salesman")

    _logger.info(
        "Permission check - is_admin: %s, stock: %s, sales: %s",
        is_admin, has_stock, has_sales
    )

    if has_stock:
        items.append(MenuItem(key="inventory", label="Inventory", deep_link="app://inventory"))
    if has_sales:
        items.append(MenuItem(key="sales", label="Sales", deep_link="app://sales"))

    items.append(MenuItem(key="settings", label="Settings", deep_link="app://settings"))

    _logger.info("Returning %d menu items: %s", len(items), [i.key for i in items])

    return MenuResponse(items=items)
