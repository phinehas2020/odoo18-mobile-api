"""Explicit contracts for the online-only packing workflow."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PackingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=200, strict=True)


class PackingBarcode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barcode: str = Field(min_length=1, max_length=512, strict=True)
    symbology: str | None = Field(default=None, max_length=80, strict=True)


class PackingResolveRequest(PackingRequest):
    barcode: str | None = Field(default=None, min_length=1, max_length=512, strict=True)
    symbology: str | None = Field(default=None, max_length=80, strict=True)
    candidates: list[PackingBarcode] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def require_scan(self):
        if not self.barcode and not self.candidates:
            raise ValueError("Provide a barcode or at least one candidate.")
        if self.symbology and not self.barcode:
            raise ValueError("A symbology without a barcode is not a scan.")
        if len(self.scans()) > 8:
            raise ValueError("Provide at most eight distinct scan candidates.")
        return self

    def scans(self):
        values = list(self.candidates)
        if self.barcode:
            values.insert(0, PackingBarcode(barcode=self.barcode, symbology=self.symbology))
        unique = {}
        for scan in values:
            unique.setdefault((scan.barcode, scan.symbology), scan)
        return list(unique.values())


class PackingActionRequest(PackingRequest):
    version: int = Field(ge=1, strict=True)
    event_id: UUID


class PackingClaimRequest(PackingActionRequest):
    user_id: int | None = Field(default=None, ge=1, strict=True)


class PackingQuantityRequest(PackingActionRequest):
    quantity: float = Field(ge=0, allow_inf_nan=False, strict=True)

    @field_validator("quantity")
    @classmethod
    def require_whole_units(cls, quantity):
        if not quantity.is_integer():
            raise ValueError("Confirm a whole item quantity.")
        return quantity


class PackingCompleteRequest(PackingActionRequest, PackingBarcode):
    pass


class PackingOwner(BaseModel):
    id: int
    name: str


class PackingItem(BaseModel):
    line_id: int
    title: str
    variant_title: str | None = None
    sku: str | None = None
    barcode: str | None = None
    product_id: int | None = None
    required_quantity: float
    confirmed_quantity: float
    remaining_quantity: float


PackingState = Literal["unstarted", "in_progress", "packed", "review", "void"]


class PackingSibling(BaseModel):
    shipment_id: int
    box_number: int
    packing_state: PackingState


class PackingAllowedActions(BaseModel):
    claim: bool
    edit: bool
    complete: bool


class PackingDetail(BaseModel):
    shipment_id: int
    order_id: int
    order_name: str
    customer_name: str | None = None
    tracking_number: str
    carrier: str | None = None
    box_number: int
    box_count: int
    packing_state: PackingState
    operational_state: Literal["pending", "complete", "review"]
    sync_state: Literal["not_ready", "pending", "submitting", "synced", "review"]
    version: int
    workflow_version: Literal["legacy_print", "packing_v1", "review"]
    owner: PackingOwner | None = None
    completed_at: datetime | None = None
    items: list[PackingItem]
    siblings: list[PackingSibling]
    allowed_actions: PackingAllowedActions
    review_reason: str | None = None
    resolved_barcode: str | None = None
    resolved_symbology: str | None = None

    @field_validator("completed_at")
    @classmethod
    def explicit_utc_timestamp(cls, value):
        # Odoo stores UTC without a timezone; make its API meaning explicit.
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class PackingCapabilities(BaseModel):
    enabled: bool
    business_enabled: bool
    can_pack: bool
    can_supervise: bool
    requires_online: bool = True
    workflow_version: Literal["packing_v1"] = "packing_v1"
