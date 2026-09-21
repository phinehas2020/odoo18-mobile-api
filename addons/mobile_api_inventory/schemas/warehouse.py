from typing import List, Optional

from pydantic import BaseModel, Field


class StockItem(BaseModel):
    id: int
    product_id: int
    product_name: str
    barcode: Optional[str] = None
    location_id: int
    location_name: str
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None
    quantity: float
    reserved_quantity: float
    uom_name: Optional[str] = None


class StockLookupResponse(BaseModel):
    items: List[StockItem]
    limit: int
    can_adjust: bool
    can_scrap: bool


class AdjustmentReviewRequest(BaseModel):
    quant_id: int
    counted_quantity: float = Field(ge=0)


class AdjustmentReviewResponse(BaseModel):
    quant_id: int
    product_id: int
    product_name: str
    location_id: int
    location_name: str
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None
    current_quantity: float
    counted_quantity: float
    difference: float
    record_version: str
    reviewed: bool
    message: Optional[str] = None
    status: Optional[str] = None


class AdjustmentApplyRequest(AdjustmentReviewRequest):
    event_id: str
    device_id: str
    record_version: str
    reviewed: bool


class ScrapReviewRequest(BaseModel):
    quant_id: int
    quantity: float = Field(gt=0)
    picking_id: Optional[int] = None


class ScrapReviewResponse(BaseModel):
    quant_id: int
    product_id: int
    product_name: str
    source_location_id: int
    source_location_name: str
    scrap_location_id: int
    scrap_location_name: str
    lot_id: Optional[int] = None
    lot_name: Optional[str] = None
    available_quantity: float
    scrap_quantity: float
    record_version: str
    reviewed: bool
    message: Optional[str] = None
    status: Optional[str] = None
    scrap_id: Optional[int] = None
    state: Optional[str] = None


class ScrapApplyRequest(ScrapReviewRequest):
    event_id: str
    device_id: str
    record_version: str
    reviewed: bool


class ReturnLine(BaseModel):
    move_id: int
    product_id: int
    product_name: str
    quantity: float
    uom_name: Optional[str] = None


class ReturnReviewResponse(BaseModel):
    picking_id: int
    picking_name: str
    record_version: str
    lines: List[ReturnLine]
    message: Optional[str] = None


class ReturnApplyLine(BaseModel):
    move_id: int
    quantity: float = Field(ge=0)


class ReturnApplyRequest(BaseModel):
    event_id: str
    device_id: str
    record_version: str
    reviewed: bool
    lines: List[ReturnApplyLine]


class ReturnApplyResponse(BaseModel):
    status: str
    original_picking_id: int
    new_picking_id: int
    new_picking_name: str
    state: str
