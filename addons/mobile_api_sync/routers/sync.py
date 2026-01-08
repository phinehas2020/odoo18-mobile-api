from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.sync import (
    SyncActionResult,
    SyncBootstrapResponse,
    SyncChange,
    SyncChangesResponse,
    SyncPushRequest,
    SyncPushResponse,
)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/bootstrap", response_model=SyncBootstrapResponse)
def bootstrap(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SyncBootstrapResponse:
    service = env["mobile.sync.service"].sudo()
    reference = service.get_bootstrap_reference(env.user)
    return SyncBootstrapResponse(cursor=service.current_cursor(), reference=reference)


@router.get("/changes", response_model=SyncChangesResponse)
def changes(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    cursor: int = Query(0),
    models: Optional[str] = Query(None),
) -> SyncChangesResponse:
    service = env["mobile.sync.service"].sudo()
    models_filter: List[str] | None = None
    if models:
        models_filter = [model.strip() for model in models.split(",") if model.strip()]
    changes_payload, new_cursor = service.get_changes(cursor, models_filter)
    changes = [SyncChange(**change) for change in changes_payload]
    return SyncChangesResponse(cursor=new_cursor, changes=changes)


@router.post("/push", response_model=SyncPushResponse)
def push(
    payload: SyncPushRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SyncPushResponse:
    service = env["mobile.sync.service"].sudo()
    actions = [action.dict() for action in payload.actions]
    results_payload = service.handle_actions(payload.device_id, actions)
    results = [SyncActionResult(**result) for result in results_payload]
    return SyncPushResponse(results=results)
