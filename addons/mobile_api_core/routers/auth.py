from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from odoo.api import Environment

from odoo.addons.fastapi.dependencies import odoo_env
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.auth import (
    AuthTokensResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RevokeRequest,
)
from ..schemas.common import CompanyInfo, UserProfile
from ..services.auth_service import MobileAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _user_profile(user, company_id=None):
    return UserProfile(
        id=user.id,
        name=user.name,
        login=user.login,
        email=user.email,
        company_id=company_id if company_id is not None else (user.company_id.id if user.company_id else None),
        allowed_company_ids=user.company_ids.ids,
        group_ids=user.groups_id.ids,
        is_admin=user.has_group("base.group_system"),
    )


def _company_info(user):
    return [
        CompanyInfo(
            id=company.id,
            name=company.name,
            currency_id=company.currency_id.id if company.currency_id else None,
        )
        for company in user.company_ids
    ]


@router.post("/login", response_model=AuthTokensResponse)
def login(
    payload: LoginRequest,
    request: Request,
    env: Annotated[Environment, Depends(odoo_env)],
) -> AuthTokensResponse:
    service = MobileAuthService(env)
    ip_address = _get_client_ip(request)
    try:
        service.check_login_rate_limit(payload.login, ip_address)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    user = service.authenticate(payload.db, payload.login, payload.password)
    if not user:
        service.record_login_attempt(payload.login, ip_address, payload.device_id, False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    service.record_login_attempt(payload.login, ip_address, payload.device_id, True)
    try:
        access_token, refresh_token, expires_in, company_id = service.issue_tokens(
            user, payload.device_id, payload.device_name, payload.company_id
        )
    except ValueError as exc:
        if str(exc) == "device_revoked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device has been revoked",
            )
        raise
    return AuthTokensResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=_user_profile(user, company_id),
        companies=_company_info(user),
    )


@router.post("/refresh", response_model=AuthTokensResponse)
def refresh(
    payload: RefreshRequest,
    env: Annotated[Environment, Depends(odoo_env)],
) -> AuthTokensResponse:
    service = MobileAuthService(env)
    result = service.refresh_tokens(
        payload.refresh_token, payload.device_id, payload.company_id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    access_token, refresh_token, expires_in, user, company_id = result
    return AuthTokensResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=_user_profile(user, company_id),
        companies=_company_info(user),
    )


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    env: Annotated[Environment, Depends(odoo_env)],
):
    service = MobileAuthService(env)
    revoked = service.revoke_refresh_token(payload.refresh_token, payload.device_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found",
        )
    return {"status": "ok"}


@router.post("/revoke")
def revoke(
    payload: RevokeRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
):
    if not env.user.has_group("base.group_system"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    service = MobileAuthService(env)
    revoked_count = service.revoke_sessions(payload.user_id, payload.device_id)
    return {"revoked": revoked_count}
