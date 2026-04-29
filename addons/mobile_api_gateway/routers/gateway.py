import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.gateway import (
    GatewayManifest,
    GatewayMethodRequest,
    GatewayMethodResponse,
    GatewayModelDetail,
    GatewayModelList,
    GatewayRecordDetail,
    GatewayRecordList,
    GatewayWriteRequest,
)
from ..services.gateway_service import (
    GatewayAccessError,
    GatewayBadRequest,
    GatewayNotFound,
    MobileGatewayService,
)

router = APIRouter(prefix="/gateway", tags=["gateway"])
_logger = logging.getLogger(__name__)


def _raise_http(exc):
    if isinstance(exc, GatewayAccessError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, GatewayNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, GatewayBadRequest):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    _logger.exception("mobile_api.gateway.unhandled_error")
    raise exc


@router.get("/manifest", response_model=GatewayManifest)
def manifest(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> GatewayManifest:
    _logger.info("mobile_api.gateway.manifest.start user_id=%s", env.user.id)
    service = MobileGatewayService(env)
    result = service.manifest()
    _logger.info(
        "mobile_api.gateway.manifest.success user_id=%s models=%s workflows=%s",
        env.user.id,
        len(result.get("models", [])),
        len(result.get("workflows", [])),
    )
    return GatewayManifest(**result)


@router.get("/models", response_model=GatewayModelList)
def models(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    search: Optional[str] = Query(None),
) -> GatewayModelList:
    service = MobileGatewayService(env)
    return GatewayModelList(models=service.models(search=search))


@router.get("/models/{model_name}", response_model=GatewayModelDetail)
def model_detail(
    model_name: str,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> GatewayModelDetail:
    service = MobileGatewayService(env)
    try:
        return GatewayModelDetail(**service.model_detail(model_name))
    except Exception as exc:
        _raise_http(exc)


@router.get("/models/{model_name}/records", response_model=GatewayRecordList)
def list_records(
    model_name: str,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    search: Optional[str] = Query(None),
    domain: Optional[str] = Query(None, description="JSON encoded Odoo domain"),
    fields: Optional[str] = Query(None, description="Comma-separated field names"),
    order: Optional[str] = Query(None),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GatewayRecordList:
    service = MobileGatewayService(env)
    try:
        return GatewayRecordList(**service.list_records(
            model_name=model_name,
            search=search,
            domain_json=domain,
            field_csv=fields,
            order=order,
            limit=limit,
            offset=offset,
        ))
    except Exception as exc:
        _raise_http(exc)


@router.get("/models/{model_name}/records/{record_id}", response_model=GatewayRecordDetail)
def get_record(
    model_name: str,
    record_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    fields: Optional[str] = Query(None, description="Comma-separated field names"),
) -> GatewayRecordDetail:
    service = MobileGatewayService(env)
    try:
        return GatewayRecordDetail(**service.get_record(model_name, record_id, field_csv=fields))
    except Exception as exc:
        _raise_http(exc)


@router.post("/models/{model_name}/records", response_model=GatewayRecordDetail)
def create_record(
    model_name: str,
    payload: GatewayWriteRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> GatewayRecordDetail:
    service = MobileGatewayService(env)
    try:
        return GatewayRecordDetail(**service.create_record(model_name, payload.values))
    except Exception as exc:
        _raise_http(exc)


@router.patch("/models/{model_name}/records/{record_id}", response_model=GatewayRecordDetail)
def update_record(
    model_name: str,
    record_id: int,
    payload: GatewayWriteRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> GatewayRecordDetail:
    service = MobileGatewayService(env)
    try:
        return GatewayRecordDetail(**service.update_record(model_name, record_id, payload.values))
    except Exception as exc:
        _raise_http(exc)


@router.post("/models/{model_name}/records/{record_id}/methods/{method_name}", response_model=GatewayMethodResponse)
def call_method(
    model_name: str,
    record_id: int,
    method_name: str,
    payload: GatewayMethodRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> GatewayMethodResponse:
    service = MobileGatewayService(env)
    try:
        return GatewayMethodResponse(**service.call_method(
            model_name=model_name,
            record_id=record_id,
            method_name=method_name,
            args=payload.args,
            kwargs=payload.kwargs,
        ))
    except Exception as exc:
        _raise_http(exc)
