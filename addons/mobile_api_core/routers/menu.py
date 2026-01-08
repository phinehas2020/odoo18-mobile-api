from typing import Annotated

from fastapi import APIRouter, Depends

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.menu import MenuItem, MenuResponse

router = APIRouter(tags=["core"])


@router.get("/menu", response_model=MenuResponse)
def menu(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> MenuResponse:
    user = env.user
    items = []

    if user.has_group("stock.group_stock_user"):
        items.append(MenuItem(key="inventory", label="Inventory", deep_link="app://inventory"))
    if user.has_group("sales_team.group_sale_salesman"):
        items.append(MenuItem(key="sales", label="Sales", deep_link="app://sales"))

    items.append(MenuItem(key="settings", label="Settings", deep_link="app://settings"))

    return MenuResponse(items=items)
