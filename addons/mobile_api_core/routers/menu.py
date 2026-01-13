import logging
from typing import Annotated
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, Request

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.menu import MenuItem, MenuResponse

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])

# Modules with native mobile views (key -> deep_link)
NATIVE_MODULES = {
    "stock": ("inventory", "app://inventory"),
    "sale": ("sales", "app://sales"),
    "inventory": ("inventory", "app://inventory"),
    "sales": ("sales", "app://sales"),
}


def _get_module_key(menu):
    """Extract module key from menu's web_icon or action."""
    # Try to get from web_icon (format: "module_name,static/description/icon.png")
    if menu.web_icon:
        parts = menu.web_icon.split(",")
        if parts:
            return parts[0]
    # Try to get from action's res_model
    if menu.action and hasattr(menu.action, "res_model"):
        model = menu.action.res_model or ""
        return model.split(".")[0] if model else None
    return None


@router.get("/menu", response_model=MenuResponse)
def menu(
    request: Request,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> MenuResponse:
    user = env.user
    items = []

    _logger.info("Menu request - User: %s (id=%s)", user.login, user.id)

    # Get base URL for web links
    base_url = env["ir.config_parameter"].sudo().get_param("web.base.url", "")

    # Get root-level menus (main apps) that user has access to
    Menu = env["ir.ui.menu"]
    root_menus = Menu.search([
        ("parent_id", "=", False),
    ], order="sequence, id")

    _logger.info("Found %d root menus", len(root_menus))

    for menu_item in root_menus:
        module_key = _get_module_key(menu_item) or menu_item.name.lower().replace(" ", "_")

        # Check if this module has native mobile support
        native_info = NATIVE_MODULES.get(module_key)
        if native_info:
            key, deep_link = native_info
            native = True
        else:
            key = module_key
            deep_link = None
            native = False

        # Build web URL for non-native modules
        web_url = None
        if menu_item.action:
            action_id = menu_item.action.id
            web_url = urljoin(base_url, f"/web#action={action_id}")
        elif base_url:
            web_url = urljoin(base_url, f"/web#menu_id={menu_item.id}")

        items.append(MenuItem(
            key=key,
            label=menu_item.name,
            enabled=True,
            deep_link=deep_link,
            icon=menu_item.web_icon or None,
            web_url=web_url,
            native=native,
        ))

    # Always add settings at the end
    items.append(MenuItem(
        key="settings",
        label="Settings",
        enabled=True,
        deep_link="app://settings",
        native=True,
    ))

    _logger.info("Returning %d menu items: %s", len(items), [i.key for i in items])

    return MenuResponse(items=items)
