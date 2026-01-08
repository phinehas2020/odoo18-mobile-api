from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from odoo import fields
from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.sales import (
    CustomerItem,
    SaleOrderDetail,
    SaleOrderItem,
    SalesNoteRequest,
)
from ..services.sales_service import MobileSalesService

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("/customers", response_model=List[CustomerItem])
def customers(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    search: Optional[str] = Query(None),
) -> List[CustomerItem]:
    service = MobileSalesService(env)
    customers = service.search_customers(search)
    return [CustomerItem(**item) for item in customers]


@router.get("/orders", response_model=List[SaleOrderItem])
def orders(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    state: Optional[str] = Query(None),
    updated_since: Optional[str] = Query(None),
) -> List[SaleOrderItem]:
    service = MobileSalesService(env)
    states = [s.strip() for s in state.split(",")] if state else None
    updated_since_dt = (
        fields.Datetime.to_datetime(updated_since) if updated_since else None
    )
    items = service.list_orders(states, updated_since_dt)
    return [SaleOrderItem(**item) for item in items]


@router.get("/orders/{order_id}", response_model=SaleOrderDetail)
def order_detail(
    order_id: int,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> SaleOrderDetail:
    service = MobileSalesService(env)
    detail = service.get_order(order_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return SaleOrderDetail(**detail)


@router.post("/orders/{order_id}/note")
def add_note(
    order_id: int,
    payload: SalesNoteRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
):
    service = MobileSalesService(env)
    ok = service.add_note(order_id, payload.note)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"status": "ok"}
