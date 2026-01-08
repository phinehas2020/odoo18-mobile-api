from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.barcode import BarcodeResolveResponse
from ..services.inventory_service import MobileInventoryService

router = APIRouter(tags=["barcode"])


@router.get("/barcode/resolve", response_model=BarcodeResolveResponse)
def resolve(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    code: str = Query(...),
) -> BarcodeResolveResponse:
    service = MobileInventoryService(env)
    resolved = service.resolve_barcode(code)
    if not resolved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return BarcodeResolveResponse(**resolved)
