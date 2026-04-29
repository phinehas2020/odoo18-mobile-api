from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_odoo_text(value):
    # Odoo returns ``False`` for unset Char/Text fields; treat as missing.
    if value is False or value == "":
        return None
    return value


OdooText = Annotated[Optional[str], BeforeValidator(_coerce_odoo_text)]


class SmartLabelJobItem(BaseModel):
    id: int
    name: str
    state: str
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    label_type: str
    requested_at: Optional[datetime] = None
    requested_by_name: OdooText = None
    device_id: Optional[int] = None
    device_name: OdooText = None
    result_message: OdooText = None
    manufacturing_order_id: Optional[int] = None
    manufacturing_order_name: OdooText = None


class SmartLabelDeviceItem(BaseModel):
    id: int
    name: str
    state: str
    stock_location_name: OdooText = None
    inventory_operation: OdooText = None
    last_seen_at: Optional[datetime] = None
    active: Optional[bool] = None


class SmartLabelProductItem(BaseModel):
    id: int
    display_name: str
    default_code: OdooText = None
    barcode: OdooText = None
    price: Optional[float] = None
    uom_name: OdooText = None
    has_profile: Optional[bool] = None


class SmartLabelQueueJobRequest(BaseModel):
    product_id: int
    device_id: Optional[int] = None
    barcode: Optional[str] = Field(default=None, max_length=128)
    quantity: int = Field(default=1, ge=1)
    label_type: Literal["back", "front", "both"] = "both"
    update_inventory: bool = True
    create_manufacturing_order: bool = False
    manufacturing_user_id: Optional[int] = None


class SmartLabelQueueJobResponse(BaseModel):
    job: SmartLabelJobItem


class SmartLabelWorkflowRequest(BaseModel):
    client_action_id: Optional[str] = Field(default=None, max_length=128)


class SmartLabelJobActionResponse(BaseModel):
    status: str
    job: SmartLabelJobItem


class SmartLabelRotateTokenResponse(BaseModel):
    status: str
    device: SmartLabelDeviceItem
    agent_token: str


class SmartLabelLink(BaseModel):
    rel: str
    href: str
    method: str = "GET"


class SmartLabelNativeTarget(BaseModel):
    model: str
    res_id: int
    native_route: Optional[str] = None
    links: List[SmartLabelLink] = Field(default_factory=list)


class SmartLabelManufacturingOrderItem(BaseModel):
    id: int
    name: str
    state: OdooText = None
    product_id: Optional[int] = None
    product_name: OdooText = None
    quantity: Optional[float] = None
    assigned_user_id: Optional[int] = None
    assigned_user_name: OdooText = None


class SmartLabelOpenManufacturingOrderResponse(BaseModel):
    status: str
    job: SmartLabelJobItem
    manufacturing_order: SmartLabelManufacturingOrderItem
    target: SmartLabelNativeTarget
