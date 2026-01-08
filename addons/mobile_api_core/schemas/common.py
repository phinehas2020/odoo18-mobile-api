from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CompanyInfo(BaseModel):
    id: int
    name: str
    currency_id: int | None = None


class UserProfile(BaseModel):
    id: int
    name: str
    login: str
    email: Optional[str] = None
    company_id: int | None = None
    allowed_company_ids: List[int]
    group_ids: List[int]
    is_admin: bool = False


class HealthResponse(BaseModel):
    status: str
    server_time: datetime
    version: str | None = None
