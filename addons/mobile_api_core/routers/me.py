import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.common import UserProfile

router = APIRouter(tags=["core"])
_logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserProfile)
def me(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> UserProfile:
    user = env.user
    _logger.info(
        "mobile_api.core.me user_id=%s login=%s company_id=%s groups=%s",
        user.id,
        user.login,
        user.company_id.id if user.company_id else None,
        len(user.groups_id),
    )
    return UserProfile(
        id=user.id,
        name=user.name,
        login=user.login,
        email=user.email,
        company_id=user.company_id.id if user.company_id else None,
        allowed_company_ids=user.company_ids.ids,
        group_ids=user.groups_id.ids,
        is_admin=user.has_group("base.group_system"),
    )
