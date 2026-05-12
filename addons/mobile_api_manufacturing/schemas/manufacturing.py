from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ManufacturingComponentItem(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: float
    reserved_quantity: Optional[float] = None
    done_quantity: Optional[float] = None
    uom_name: Optional[str] = None


class ManufacturingOrderItem(BaseModel):
    id: int
    name: str
    state: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    uom_name: Optional[str] = None
    planned_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    assigned_user_name: Optional[str] = None
    attention_reason: Optional[str] = None


class ManufacturingOrderDetail(ManufacturingOrderItem):
    origin: Optional[str] = None
    bom_name: Optional[str] = None
    components: List[ManufacturingComponentItem] = []


class ManufacturingOrderCreateRequest(BaseModel):
    product_id: int
    quantity: float = Field(default=1, gt=0)
    deadline: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class ManufacturingOrderCreateResponse(BaseModel):
    order: ManufacturingOrderItem
