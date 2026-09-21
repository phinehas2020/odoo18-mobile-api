from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PickingProgress(BaseModel):
    done: float
    total: float


class PickingListItem(BaseModel):
    id: int
    name: str
    picking_type: Optional[str] = None
    picking_type_code: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    priority: Optional[str] = None
    partner_name: Optional[str] = None
    progress: PickingProgress


class PickingLine(BaseModel):
    id: int
    move_id: int
    product_id: int
    product_name: str
    barcode: Optional[str] = None
    qty_done: float
    qty_reserved: float
    qty_demanded: float
    uom_name: Optional[str] = None
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None
    tracking: Optional[str] = None


class PickingMove(BaseModel):
    id: int
    product_id: int
    product_name: str
    barcode: Optional[str] = None
    qty_demanded: float
    qty_done: float
    uom_name: Optional[str] = None
    tracking: Optional[str] = None


class LocationInfo(BaseModel):
    id: int
    name: str
    barcode: Optional[str] = None


class PickingDetail(BaseModel):
    id: int
    name: str
    state: str
    picking_type: Optional[str] = None
    picking_type_code: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    priority: Optional[str] = None
    partner_name: Optional[str] = None
    source_location: LocationInfo
    dest_location: LocationInfo
    record_version: Optional[str] = None
    moves: List[PickingMove]
    lines: List[PickingLine]


class ScanRequest(BaseModel):
    event_id: str
    code: str
    qty: Optional[float] = Field(default=None, gt=0)
    timestamp: Optional[datetime] = None
    device_id: str
    record_version: Optional[str] = None


class ScanResponse(BaseModel):
    status: str
    updated_lines: List[PickingLine]
    warnings: List[str] = []
    next_expected: Optional[str] = None
    record_version: Optional[str] = None


class ValidateRequest(BaseModel):
    event_id: str
    device_id: str
    record_version: Optional[str] = None
    backorder_policy: Literal["ask", "create", "cancel"] = "ask"


class ValidateResponse(BaseModel):
    status: str
    picking_state: Optional[str] = None
    record_version: Optional[str] = None
    backorder_required: bool = False
    backorder_picking_id: Optional[int] = None
    message: Optional[str] = None


class UpdatePickingLineRequest(BaseModel):
    event_id: str
    device_id: str
    qty_done: float = Field(ge=0)
    record_version: Optional[str] = None
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None


class UpdatePickingLineResponse(BaseModel):
    status: str
    line: PickingLine
    record_version: Optional[str] = None
    warnings: List[str] = []


class CreatePickingLineRequest(UpdatePickingLineRequest):
    move_id: int
