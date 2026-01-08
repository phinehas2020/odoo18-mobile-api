from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    platform: str = "ios"
    model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None
    push_token: Optional[str] = None


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    push_token: Optional[str] = None


class DeviceResponse(BaseModel):
    device_id: str
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
