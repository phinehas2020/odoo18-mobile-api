from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, Response

from odoo.api import Environment
from odoo.addons.fastapi_auth_jwt.dependencies import (
    auth_jwt_authenticated_odoo_env,
    auth_jwt_authenticated_payload,
)
from odoo.addons.shopify_fulfillment.services.packing_utils import PACKING_MOBILE_REQUEST

from ..schemas.packing import (
    PackingCapabilities,
    PackingClaimRequest,
    PackingCompleteRequest,
    PackingDetail,
    PackingQuantityRequest,
    PackingResolveRequest,
)
from ..services.packing_service import MobilePackingService, reject, validate_token_scope


router = APIRouter(prefix="/shopify/packing", tags=["packing"])


def packing_service(
    request: Request,
    response: Response,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    payload: Annotated[dict, Depends(auth_jwt_authenticated_payload)],
) -> MobilePackingService:
    # Require a mobile access token, even if another JWT validator allows cookies.
    if not request.headers.get("authorization", "").lower().startswith("bearer "):
        reject("access_token_required", "Sign in again to use packing.", 401)
    if not env.user.active or env.user.share:
        reject("packing_permission_required", "An active employee account is required.")
    company_id, device_id = validate_token_scope(payload, env.user.id, env.user.company_ids.ids)
    request_device = request.headers.get("x-device-id")
    if request_device is not None and request_device != device_id:
        reject("device_mismatch", "This request belongs to a different device.")
    # Device registry permissions are intentionally administrative; read exactly
    # this signed identity to verify revocation and ownership, never records to pack.
    device = env["mobile.device"].sudo().search([("device_id", "=", device_id)], limit=1)
    if not device or device.revoked_at or device.user_id.id != env.user.id:
        reject("device_revoked", "Sign in again on an authorized device.", 401)
    context = dict(
        env.context,
        allowed_company_ids=[company_id],
        mobile_device_id=device_id,
        _packing_mobile_request=PACKING_MOBILE_REQUEST,
    )
    scoped_env = env(user=env.user.id, context=context, su=False)
    response.headers["Cache-Control"] = "no-store"
    return MobilePackingService(scoped_env, device_id)


PackingService = Annotated[MobilePackingService, Depends(packing_service)]
ShipmentID = Annotated[int, Path(ge=1)]
DeviceHeader = Annotated[str | None, Header(alias="X-Device-ID")]


@router.get("/capabilities", response_model=PackingCapabilities)
def capabilities(service: PackingService, device_id: DeviceHeader = None):
    service.bind_device(device_id)
    return service.capabilities()


@router.post("/resolve", response_model=PackingDetail, response_model_exclude_none=True)
def resolve(payload: PackingResolveRequest, service: PackingService):
    service.authorize(payload.device_id)
    return service.resolve(payload.scans())


@router.get("/{shipment_id}", response_model=PackingDetail, response_model_exclude_none=True)
def detail(shipment_id: ShipmentID, service: PackingService, device_id: DeviceHeader = None):
    service.authorize(device_id)
    return service.call(service.shipment(shipment_id).packing_detail)


@router.post("/{shipment_id}/claim", response_model=PackingDetail, response_model_exclude_none=True)
def claim(shipment_id: ShipmentID, payload: PackingClaimRequest, service: PackingService):
    service.authorize(payload.device_id, mutation=True)
    return service.call(
        service.shipment(shipment_id).packing_claim,
        payload.version,
        str(payload.event_id),
        payload.device_id,
        user_id=payload.user_id,
    )


@router.patch("/{shipment_id}/items/{line_id}", response_model=PackingDetail, response_model_exclude_none=True)
def quantity(
    shipment_id: ShipmentID,
    line_id: Annotated[int, Path(ge=1)],
    payload: PackingQuantityRequest,
    service: PackingService,
):
    service.authorize(payload.device_id, mutation=True)
    return service.call(
        service.shipment(shipment_id).packing_set_quantity,
        line_id,
        int(payload.quantity),
        payload.version,
        str(payload.event_id),
        payload.device_id,
    )


@router.post("/{shipment_id}/complete", response_model=PackingDetail, response_model_exclude_none=True)
def complete(shipment_id: ShipmentID, payload: PackingCompleteRequest, service: PackingService):
    service.authorize(payload.device_id, mutation=True)
    return service.call(
        service.shipment(shipment_id).packing_complete,
        payload.barcode,
        payload.symbology,
        payload.version,
        str(payload.event_id),
        payload.device_id,
    )
