from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ManufacturingLotQuantityItem(BaseModel):
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None
    quantity: float


class ManufacturingComponentItem(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: float
    reserved_quantity: Optional[float] = None
    done_quantity: Optional[float] = None
    uom_name: Optional[str] = None
    tracking: str = "none"
    picked: bool = False
    lot_quantities: List[ManufacturingLotQuantityItem] = Field(default_factory=list)


class ManufacturingLotItem(BaseModel):
    id: int
    name: str


class ManufacturingProductItem(BaseModel):
    id: int
    name: str
    tracking: str = "none"
    uom_name: Optional[str] = None


class ManufacturingWorkOrderItem(BaseModel):
    id: int
    name: str
    state: str
    workcenter_name: Optional[str] = None
    employee_name: Optional[str] = None
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
    has_photo: bool = False


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
    quantity_producing: Optional[float] = None
    quantity_remaining: Optional[float] = None
    product_tracking: str = "none"
    finished_lot_id: Optional[int] = None
    finished_lot_name: Optional[str] = None


class ManufacturingAssigneeItem(BaseModel):
    id: int
    name: str
    login: Optional[str] = None
    email: Optional[str] = None


class ManufacturingOrderDetail(ManufacturingOrderItem):
    origin: Optional[str] = None
    bom_name: Optional[str] = None
    components: List[ManufacturingComponentItem] = Field(default_factory=list)
    workorders: List[ManufacturingWorkOrderItem] = Field(default_factory=list)
    quality_checks: List[ManufacturingQualityCheckItem] = Field(default_factory=list)


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


class ManufacturingQualityCheckPhotoRequest(BaseModel):
    image_base64: str = Field(min_length=4, max_length=7_100_000)
    filename: str = Field(default="quality-check.jpg", min_length=1, max_length=150)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ManufacturingComponentConsumptionRequest(BaseModel):
    move_id: int
    quantity: float = Field(ge=0)
    lot_id: Optional[int] = None


class ManufacturingOrderCompleteRequest(BaseModel):
    reviewed: bool
    quantity: float = Field(gt=0)
    disposition: Literal["close", "backorder"]
    finished_lot_id: Optional[int] = None
    finished_lot_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    components: List[ManufacturingComponentConsumptionRequest] = Field(default_factory=list)


class ManufacturingCompletionReview(BaseModel):
    order_id: int
    can_complete: bool
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggested_quantity: float
    quantity_remaining: float
    requires_finished_lot: bool
    open_workorder_ids: List[int] = Field(default_factory=list)
    pending_quality_check_ids: List[int] = Field(default_factory=list)
