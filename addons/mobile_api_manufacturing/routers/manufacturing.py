import logging
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.manufacturing import (
    ManufacturingAssigneeItem,
    ManufacturingOrderCreateRequest,
    ManufacturingOrderCreateResponse,
    ManufacturingOrderDetail,
    ManufacturingOrderItem,
    ManufacturingQualityCheckActionRequest,
)
from ..services.manufacturing_service import MobileManufacturingService

router = APIRouter(prefix="/manufacturing", tags=["manufacturing"])
_logger = logging.getLogger(__name__)


def _payload_dict(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload.dict(exclude_none=True)


def _raise_http(exc, operation, user_id, **context):
    if isinstance(exc, MissingError):
        _logger.warning(
            "mobile_api.manufacturing.%s.route.not_found user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, AccessError):
        _logger.warning(
            "mobile_api.manufacturing.%s.route.access_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValidationError):
        _logger.warning(
            "mobile_api.manufacturing.%s.route.validation_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if isinstance(exc, UserError):
        _logger.warning(
            "mobile_api.manufacturing.%s.route.user_error user_id=%s context=%s message=%s",
            operation,
            user_id,
            context,
            str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _logger.exception(
        "mobile_api.manufacturing.%s.route.unexpected_error user_id=%s context=%s",
        operation,
        user_id,
        context,
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected manufacturing workflow error",
    )


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


@router.get("/assignees", response_model=List[ManufacturingAssigneeItem])
def assignees(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    limit: int = Query(100, ge=1, le=200),
) -> List[ManufacturingAssigneeItem]:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.assignees.route.start user_id=%s limit=%s",
        env.user.id,
        limit,
    )
    items = service.list_assignees(limit=limit)
    _logger.info(
        "mobile_api.manufacturing.assignees.route.success user_id=%s count=%s",
        env.user.id,
        len(items),
    )
    return [ManufacturingAssigneeItem(**item) for item in items]


@router.post("/orders", response_model=ManufacturingOrderCreateResponse)
def create_order(
    payload: ManufacturingOrderCreateRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderCreateResponse:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.create.route.start user_id=%s product_id=%s quantity=%s assigned_user_id=%s",
        env.user.id,
        payload.product_id,
        payload.quantity,
        payload.assigned_user_id,
    )
    try:
        order = service.create_order(_payload_dict(payload))
    except Exception as exc:
        _raise_http(
            exc,
            "create",
            env.user.id,
            product_id=payload.product_id,
            assigned_user_id=payload.assigned_user_id,
        )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    _logger.info(
        "mobile_api.manufacturing.create.route.success user_id=%s order_id=%s",
        env.user.id,
        order["id"],
    )
    return ManufacturingOrderCreateResponse(order=ManufacturingOrderItem(**order))


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


@router.post("/orders/{order_id}/plan", response_model=ManufacturingOrderDetail)
def plan_order(
    order_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.plan.route.start user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    try:
        detail = service.plan_order(order_id)
    except Exception as exc:
        _raise_http(exc, "plan", env.user.id, order_id=order_id)
    _logger.info(
        "mobile_api.manufacturing.plan.route.success user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    return ManufacturingOrderDetail(**detail)


@router.post("/orders/{order_id}/complete", response_model=ManufacturingOrderDetail)
def complete_order(
    order_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.complete.route.start user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    try:
        detail = service.complete_order(order_id)
    except Exception as exc:
        _raise_http(exc, "complete", env.user.id, order_id=order_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    _logger.info(
        "mobile_api.manufacturing.complete.route.success user_id=%s order_id=%s",
        env.user.id,
        order_id,
    )
    return ManufacturingOrderDetail(**detail)


@router.post("/workorders/{workorder_id}/start", response_model=ManufacturingOrderDetail)
def start_workorder(
    workorder_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.workorder_start.route.start user_id=%s workorder_id=%s",
        env.user.id,
        workorder_id,
    )
    try:
        detail = service.start_workorder(workorder_id)
    except Exception as exc:
        _raise_http(exc, "workorder_start", env.user.id, workorder_id=workorder_id)
    return ManufacturingOrderDetail(**detail)


@router.post("/workorders/{workorder_id}/stop", response_model=ManufacturingOrderDetail)
def stop_workorder(
    workorder_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.workorder_stop.route.start user_id=%s workorder_id=%s",
        env.user.id,
        workorder_id,
    )
    try:
        detail = service.stop_workorder(workorder_id)
    except Exception as exc:
        _raise_http(exc, "workorder_stop", env.user.id, workorder_id=workorder_id)
    return ManufacturingOrderDetail(**detail)


@router.post("/workorders/{workorder_id}/finish", response_model=ManufacturingOrderDetail)
def finish_workorder(
    workorder_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.workorder_finish.route.start user_id=%s workorder_id=%s",
        env.user.id,
        workorder_id,
    )
    try:
        detail = service.finish_workorder(workorder_id)
    except Exception as exc:
        _raise_http(exc, "workorder_finish", env.user.id, workorder_id=workorder_id)
    return ManufacturingOrderDetail(**detail)


@router.post("/quality-checks/{check_id}/pass", response_model=ManufacturingOrderDetail)
def pass_quality_check(
    check_id: int,
    payload: ManufacturingQualityCheckActionRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.quality_pass.route.start user_id=%s check_id=%s",
        env.user.id,
        check_id,
    )
    try:
        detail = service.pass_quality_check(check_id, notes=payload.notes)
    except Exception as exc:
        _raise_http(exc, "quality_pass", env.user.id, check_id=check_id)
    return ManufacturingOrderDetail(**detail)


@router.post("/quality-checks/{check_id}/fail", response_model=ManufacturingOrderDetail)
def fail_quality_check(
    check_id: int,
    payload: ManufacturingQualityCheckActionRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> ManufacturingOrderDetail:
    service = MobileManufacturingService(env)
    _logger.info(
        "mobile_api.manufacturing.quality_fail.route.start user_id=%s check_id=%s",
        env.user.id,
        check_id,
    )
    try:
        detail = service.fail_quality_check(check_id, notes=payload.notes)
    except Exception as exc:
        _raise_http(exc, "quality_fail", env.user.id, check_id=check_id)
    return ManufacturingOrderDetail(**detail)
