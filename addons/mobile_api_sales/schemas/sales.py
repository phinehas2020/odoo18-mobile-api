from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CustomerItem(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class SaleOrderLineItem(BaseModel):
    id: int
    product_name: str
    quantity: float
    price_subtotal: float


class SaleOrderItem(BaseModel):
    id: int
    name: str
    state: str
    amount_total: float
    currency_id: int
    partner_name: Optional[str] = None
    date_order: Optional[datetime] = None


class SaleOrderDetail(BaseModel):
    id: int
    name: str
    state: str
    amount_total: float
    currency_id: int
    partner_name: Optional[str] = None
    date_order: Optional[datetime] = None
    note: Optional[str] = None
    lines: List[SaleOrderLineItem]


class SalesNoteRequest(BaseModel):
    note: str
