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


class ManufacturingWorkOrderItem(BaseModel):
    id: int
    name: str
    state: str
    workcenter_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    quantity_remaining: Optional[float] = None
    expected_duration_minutes: Optional[float] = None
    real_duration_minutes: Optional[float] = None
    is_user_working: bool = False
    working_state: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ManufacturingQualityCheckItem(BaseModel):
    id: int
    name: str
    state: str
    control_type: Optional[str] = None
    failure_action: Optional[str] = None
    notes: Optional[str] = None
    instructions: Optional[str] = None
    completed_by_name: Optional[str] = None
    completed_date: Optional[datetime] = None


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
    is_planned: Optional[bool] = None
    quality_state: Optional[str] = None
    quality_check_count: Optional[int] = None
    attention_reason: Optional[str] = None


class ManufacturingAssigneeItem(BaseModel):
    id: int
    name: str
    login: Optional[str] = None
    email: Optional[str] = None


class ManufacturingOrderDetail(ManufacturingOrderItem):
    origin: Optional[str] = None
    bom_name: Optional[str] = None
    components: List[ManufacturingComponentItem] = []
    workorders: List[ManufacturingWorkOrderItem] = []
    quality_checks: List[ManufacturingQualityCheckItem] = []


class ManufacturingOrderCreateRequest(BaseModel):
    product_id: int
    quantity: float = Field(default=1, gt=0)
    assigned_user_id: Optional[int] = None
    deadline: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class ManufacturingOrderCreateResponse(BaseModel):
    order: ManufacturingOrderItem


class ManufacturingQualityCheckActionRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=2000)
