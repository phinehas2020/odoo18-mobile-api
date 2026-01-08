from typing import Annotated

from fastapi import APIRouter, Depends

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.settings import SettingsResponse

router = APIRouter(tags=["core"])


@router.get("/settings", response_model=SettingsResponse)
def settings(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SettingsResponse:
    config = env["ir.config_parameter"].sudo()
    barcode = {
        "scan_mode": config.get_param("mobile_api.barcode.scan_mode", "camera"),
        "keyboard_wedge": config.get_param("mobile_api.barcode.keyboard_wedge", "true"),
    }
    offline = {
        "max_pending": config.get_param("mobile_api.offline.max_pending", "1000"),
        "auto_sync": config.get_param("mobile_api.offline.auto_sync", "true"),
    }
    return SettingsResponse(barcode=barcode, offline=offline)
