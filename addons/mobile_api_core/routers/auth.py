import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from odoo import fields
from odoo.api import Environment

from odoo.addons.fastapi.dependencies import odoo_env
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.auth import (
    AuthTokensResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RevokeRequest,
    WebSessionResponse,
)
from ..schemas.common import CompanyInfo, UserProfile
from ..services.auth_service import MobileAuthService

router = APIRouter(prefix="/auth", tags=["auth"])
_logger = logging.getLogger(__name__)

# In-memory store for one-time login tokens (consider Redis for production)
_login_tokens = {}


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
    _logger.info(
        "mobile_api.auth.login.route.start login=%s db=%s device_id=%s ip=%s company_id=%s",
        payload.login,
        payload.db,
        payload.device_id,
        ip_address,
        payload.company_id,
    )
    try:
        service.check_login_rate_limit(payload.login, ip_address)
    except ValueError:
        _logger.warning(
            "mobile_api.auth.login.route.rate_limited login=%s device_id=%s ip=%s",
            payload.login,
            payload.device_id,
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    user = service.authenticate(payload.db, payload.login, payload.password)
    if not user:
        service.record_login_attempt(payload.login, ip_address, payload.device_id, False)
        _logger.warning(
            "mobile_api.auth.login.route.invalid login=%s device_id=%s ip=%s",
            payload.login,
            payload.device_id,
            ip_address,
        )
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
            _logger.warning(
                "mobile_api.auth.login.route.device_revoked user_id=%s device_id=%s",
                user.id,
                payload.device_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device has been revoked",
            )
        raise
    _logger.info(
        "mobile_api.auth.login.route.success user_id=%s login=%s device_id=%s company_id=%s expires_in=%s",
        user.id,
        payload.login,
        payload.device_id,
        company_id,
        expires_in,
    )
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
    _logger.info(
        "mobile_api.auth.refresh.route.start device_id=%s company_id=%s",
        payload.device_id,
        payload.company_id,
    )
    result = service.refresh_tokens(
        payload.refresh_token, payload.device_id, payload.company_id
    )
    if not result:
        _logger.warning("mobile_api.auth.refresh.route.invalid device_id=%s", payload.device_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    access_token, refresh_token, expires_in, user, company_id = result
    _logger.info(
        "mobile_api.auth.refresh.route.success user_id=%s device_id=%s company_id=%s expires_in=%s",
        user.id,
        payload.device_id,
        company_id,
        expires_in,
    )
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
    _logger.info("mobile_api.auth.logout.route.start device_id=%s", payload.device_id)
    revoked = service.revoke_refresh_token(payload.refresh_token, payload.device_id)
    if not revoked:
        _logger.warning("mobile_api.auth.logout.route.not_found device_id=%s", payload.device_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh token not found",
        )
    _logger.info("mobile_api.auth.logout.route.success device_id=%s", payload.device_id)
    return {"status": "ok"}


@router.post("/revoke")
def revoke(
    payload: RevokeRequest,
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
):
    if not env.user.has_group("base.group_system"):
        _logger.warning("mobile_api.auth.revoke.route.forbidden requester_id=%s", env.user.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    service = MobileAuthService(env)
    revoked_count = service.revoke_sessions(payload.user_id, payload.device_id)
    _logger.info(
        "mobile_api.auth.revoke.route.success requester_id=%s user_id=%s device_id=%s revoked=%s",
        env.user.id,
        payload.user_id,
        payload.device_id,
        revoked_count,
    )
    return {"revoked": revoked_count}


@router.get("/web-session", response_model=WebSessionResponse)
def create_web_session(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
    redirect: str = Query(..., description="URL to redirect after login"),
) -> WebSessionResponse:
    """Create a one-time login token for WebView authentication.

    This endpoint creates a one-time token that the mobile app can use
    to authenticate a WebView session. The token is consumed by the
    /mobile/web-login Odoo controller which creates a proper web session.
    """
    user = env.user
    token = secrets.token_urlsafe(32)
    _logger.info(
        "mobile_api.auth.web_session.route.start user_id=%s redirect=%s",
        user.id,
        redirect,
    )

    # Store token with user info (expires in 60 seconds)
    _login_tokens[token] = {
        "user_id": user.id,
        "redirect": redirect,
        "expires": fields.Datetime.now().timestamp() + 60,
    }

    # Use the Odoo HTTP controller route for proper session handling
    base_url = env["ir.config_parameter"].sudo().get_param("web.base.url", "")
    login_url = f"{base_url}/mobile/web-login?token={token}"

    _logger.info(
        "mobile_api.auth.web_session.route.success user_id=%s redirect=%s expires_seconds=%s",
        user.id,
        redirect,
        60,
    )
    return WebSessionResponse(login_url=login_url)
