from typing import List, Optional

from pydantic import BaseModel, Field

from .common import CompanyInfo, UserProfile


class LoginRequest(BaseModel):
    db: str = Field(..., description="Odoo database name")
    login: str
    password: str
    device_id: str
    device_name: Optional[str] = None
    company_id: Optional[int] = None


class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: str
    company_id: Optional[int] = None


class LogoutRequest(BaseModel):
    refresh_token: str
    device_id: str


class RevokeRequest(BaseModel):
    user_id: Optional[int] = None
    device_id: Optional[str] = None


class AuthTokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserProfile
    companies: List[CompanyInfo]
