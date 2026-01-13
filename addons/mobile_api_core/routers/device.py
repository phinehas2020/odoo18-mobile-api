import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from odoo import fields
from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.device import DeviceHeartbeatRequest, DeviceRegisterRequest, DeviceResponse

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device", tags=["device"])


def _upsert_device(env, payload, user_id):
    try:
        device = (
            env["mobile.device"]
            .sudo()
            .search([("device_id", "=", payload.device_id)], limit=1)
        )
        if device and device.revoked_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device has been revoked",
            )
        values = {
            "user_id": user_id,
            "device_id": payload.device_id,
            "device_name": getattr(payload, "device_name", None),
            "platform": getattr(payload, "platform", "ios"),
            "model": getattr(payload, "model", None),
            "os_version": getattr(payload, "os_version", None),
            "app_version": getattr(payload, "app_version", None),
            "push_token": getattr(payload, "push_token", None),
            "last_seen_at": fields.Datetime.now(),
        }
        if device:
            device.write(values)
            return device
        return env["mobile.device"].sudo().create(values)
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("Failed to upsert device: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register device: {str(e)}",
        )


@router.post("/register", response_model=DeviceResponse)
def register(
    payload: DeviceRegisterRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> DeviceResponse:
    device = _upsert_device(env, payload, env.user.id)
    return DeviceResponse(
        device_id=device.device_id,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
    )


@router.post("/heartbeat", response_model=DeviceResponse)
def heartbeat(
    payload: DeviceHeartbeatRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> DeviceResponse:
    device = _upsert_device(env, payload, env.user.id)
    return DeviceResponse(
        device_id=device.device_id,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
    )
