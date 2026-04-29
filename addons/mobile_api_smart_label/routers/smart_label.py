import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.smart_label import (
    SmartLabelDeviceItem,
    SmartLabelJobActionResponse,
    SmartLabelJobItem,
    SmartLabelOpenManufacturingOrderResponse,
    SmartLabelProductItem,
    SmartLabelQueueJobRequest,
    SmartLabelQueueJobResponse,
    SmartLabelRotateTokenResponse,
    SmartLabelWorkflowRequest,
)
from ..services.smart_label_service import MobileSmartLabelService, SmartLabelNotFound

router = APIRouter(prefix="/smart-label", tags=["smart-label"])
_logger = logging.getLogger(__name__)


def _payload_dict(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload.dict(exclude_none=True)


def _raise_http(exc, operation, user_id, **context):
    if isinstance(exc, (SmartLabelNotFound, MissingError)):
        _logger.warning(
            "mobile_api.smart_label.%s.route.not_found user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AccessError):
        _logger.warning(
            "mobile_api.smart_label.%s.route.access_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValidationError):
        _logger.warning(
            "mobile_api.smart_label.%s.route.validation_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, UserError):
        _logger.warning(
            "mobile_api.smart_label.%s.route.user_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _logger.exception(
        "mobile_api.smart_label.%s.route.unexpected_error user_id=%s context=%s",
        operation,
        user_id,
        context,
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected smart label workflow error",
    )


@router.get("/jobs", response_model=List[SmartLabelJobItem])
def list_jobs(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[SmartLabelJobItem]:
    service = MobileSmartLabelService(env)
    state_values = [item.strip() for item in state.split(",")] if state else None
    _logger.info(
        "mobile_api.smart_label.jobs.route.start user_id=%s state=%s limit=%s",
        env.user.id,
        state_values,
        limit,
    )
    try:
        items = service.list_jobs(state_values=state_values, limit=limit)
    except Exception as exc:
        _raise_http(exc, "jobs", env.user.id, state=state_values, limit=limit)
    _logger.info("mobile_api.smart_label.jobs.route.success user_id=%s count=%s", env.user.id, len(items))
    return [SmartLabelJobItem(**item) for item in items]


@router.get("/devices", response_model=List[SmartLabelDeviceItem])
def list_devices(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> List[SmartLabelDeviceItem]:
    service = MobileSmartLabelService(env)
    _logger.info("mobile_api.smart_label.devices.route.start user_id=%s", env.user.id)
    try:
        items = service.list_devices()
    except Exception as exc:
        _raise_http(exc, "devices", env.user.id)
    _logger.info("mobile_api.smart_label.devices.route.success user_id=%s count=%s", env.user.id, len(items))
    return [SmartLabelDeviceItem(**item) for item in items]


@router.get("/products", response_model=List[SmartLabelProductItem])
def search_products(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    query: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
) -> List[SmartLabelProductItem]:
    service = MobileSmartLabelService(env)
    _logger.info("mobile_api.smart_label.products.route.start user_id=%s query_hash=%s limit=%s", env.user.id, hash(query), limit)
    try:
        items = service.search_products(query=query, limit=limit)
    except Exception as exc:
        _raise_http(exc, "products", env.user.id, limit=limit)
    _logger.info("mobile_api.smart_label.products.route.success user_id=%s count=%s", env.user.id, len(items))
    return [SmartLabelProductItem(**item) for item in items]


@router.post("/jobs", response_model=SmartLabelQueueJobResponse)
def queue_job(
    payload: SmartLabelQueueJobRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SmartLabelQueueJobResponse:
    service = MobileSmartLabelService(env)
    _logger.info(
        "mobile_api.smart_label.queue.route.start user_id=%s product_id=%s device_id=%s quantity=%s label_type=%s",
        env.user.id,
        payload.product_id,
        payload.device_id,
        payload.quantity,
        payload.label_type,
    )
    try:
        job = service.queue_job(_payload_dict(payload))
    except Exception as exc:
        _raise_http(
            exc,
            "queue",
            env.user.id,
            product_id=payload.product_id,
            device_id=payload.device_id,
        )

    item = service.job_item(job)
    _logger.info("mobile_api.smart_label.queue.route.success user_id=%s job_id=%s", env.user.id, item["id"])
    return SmartLabelQueueJobResponse(job=SmartLabelJobItem(**item))


@router.post("/jobs/{job_id}/cancel", response_model=SmartLabelJobActionResponse)
def cancel_job(
    job_id: int,
    payload: SmartLabelWorkflowRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SmartLabelJobActionResponse:
    service = MobileSmartLabelService(env)
    _logger.info(
        "mobile_api.smart_label.cancel.route.start user_id=%s job_id=%s client_action_id=%s",
        env.user.id,
        job_id,
        payload.client_action_id,
    )
    try:
        job = service.cancel_job(job_id)
    except Exception as exc:
        _raise_http(exc, "cancel", env.user.id, job_id=job_id)
    item = service.job_item(job)
    _logger.info(
        "mobile_api.smart_label.cancel.route.success user_id=%s job_id=%s state=%s",
        env.user.id,
        job_id,
        item["state"],
    )
    return SmartLabelJobActionResponse(status="success", job=SmartLabelJobItem(**item))


@router.post("/jobs/{job_id}/reset", response_model=SmartLabelJobActionResponse)
def reset_job(
    job_id: int,
    payload: SmartLabelWorkflowRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SmartLabelJobActionResponse:
    service = MobileSmartLabelService(env)
    _logger.info(
        "mobile_api.smart_label.reset.route.start user_id=%s job_id=%s client_action_id=%s",
        env.user.id,
        job_id,
        payload.client_action_id,
    )
    try:
        job = service.reset_job(job_id)
    except Exception as exc:
        _raise_http(exc, "reset", env.user.id, job_id=job_id)
    item = service.job_item(job)
    _logger.info(
        "mobile_api.smart_label.reset.route.success user_id=%s job_id=%s state=%s",
        env.user.id,
        job_id,
        item["state"],
    )
    return SmartLabelJobActionResponse(status="success", job=SmartLabelJobItem(**item))


@router.post("/jobs/{job_id}/open-manufacturing-order", response_model=SmartLabelOpenManufacturingOrderResponse)
def open_manufacturing_order(
    job_id: int,
    payload: SmartLabelWorkflowRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SmartLabelOpenManufacturingOrderResponse:
    service = MobileSmartLabelService(env)
    _logger.info(
        "mobile_api.smart_label.open_manufacturing_order.route.start user_id=%s job_id=%s client_action_id=%s",
        env.user.id,
        job_id,
        payload.client_action_id,
    )
    try:
        result = service.open_manufacturing_order(job_id)
    except Exception as exc:
        _raise_http(exc, "open_manufacturing_order", env.user.id, job_id=job_id)
    _logger.info(
        "mobile_api.smart_label.open_manufacturing_order.route.success user_id=%s job_id=%s manufacturing_order_id=%s",
        env.user.id,
        job_id,
        result["manufacturing_order"]["id"],
    )
    return SmartLabelOpenManufacturingOrderResponse(status="success", **result)


@router.post("/devices/{device_id}/rotate-token", response_model=SmartLabelRotateTokenResponse)
def rotate_device_token(
    device_id: int,
    payload: SmartLabelWorkflowRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SmartLabelRotateTokenResponse:
    service = MobileSmartLabelService(env)
    _logger.info(
        "mobile_api.smart_label.rotate_token.route.start user_id=%s device_id=%s client_action_id=%s",
        env.user.id,
        device_id,
        payload.client_action_id,
    )
    try:
        device = service.rotate_device_token(device_id)
    except Exception as exc:
        _raise_http(exc, "rotate_token", env.user.id, device_id=device_id)
    item = service.device_item(device)
    _logger.info(
        "mobile_api.smart_label.rotate_token.route.success user_id=%s device_id=%s",
        env.user.id,
        device_id,
    )
    return SmartLabelRotateTokenResponse(
        status="success",
        device=SmartLabelDeviceItem(**item),
        agent_token=device.agent_token,
    )
