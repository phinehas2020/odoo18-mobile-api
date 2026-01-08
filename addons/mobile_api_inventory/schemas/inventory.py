from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PickingProgress(BaseModel):
    done: float
    total: float


class PickingListItem(BaseModel):
    id: int
    name: str
    picking_type: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    priority: Optional[str] = None
    partner_name: Optional[str] = None
    progress: PickingProgress


class PickingLine(BaseModel):
    id: int
    product_id: int
    product_name: str
    barcode: Optional[str] = None
    qty_done: float
    qty_reserved: float
    qty_demanded: float
    uom_name: Optional[str] = None
    lot_name: Optional[str] = None
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
    scheduled_date: Optional[datetime] = None
    priority: Optional[str] = None
    partner_name: Optional[str] = None
    source_location: LocationInfo
    dest_location: LocationInfo
    record_version: Optional[str] = None
    lines: List[PickingLine]


class ScanRequest(BaseModel):
    event_id: str
    code: str
    qty: Optional[float] = None
    timestamp: Optional[datetime] = None
    device_id: str
    record_version: Optional[str] = None


class ScanResponse(BaseModel):
    status: str
    updated_lines: List[PickingLine]
    warnings: List[str] = []
    next_expected: Optional[str] = None


class ValidateRequest(BaseModel):
    event_id: str
    device_id: str
    record_version: Optional[str] = None


class ValidateResponse(BaseModel):
    status: str
