from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SyncChange(BaseModel):
    seq: int
    model: str
    res_id: int
    operation: str
    write_date: datetime | None = None
    payload_hint: Optional[str | bool] = None


class SyncChangesResponse(BaseModel):
    cursor: int
    changes: List[SyncChange]


class SyncBootstrapResponse(BaseModel):
    cursor: int
    reference: Dict[str, Any]


class OutboxAction(BaseModel):
    event_id: str
    type: str
    payload: Dict[str, Any]
    created_at: Optional[datetime] = None


class SyncPushRequest(BaseModel):
    device_id: str
    actions: List[OutboxAction]


class SyncActionResult(BaseModel):
    event_id: str
    status: str
    message: Optional[str] = None
    model: Optional[str] = None
    res_id: Optional[int] = None


class SyncPushResponse(BaseModel):
    results: List[SyncActionResult]
