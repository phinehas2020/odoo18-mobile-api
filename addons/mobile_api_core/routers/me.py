from typing import Annotated

from fastapi import APIRouter, Depends

from odoo.api import Environment

from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..schemas.common import UserProfile

router = APIRouter(tags=["core"])


@router.get("/me", response_model=UserProfile)
def me(
    env: Annotated[Environment, Depends(auth_jwt_authenticated_odoo_env)],
) -> UserProfile:
    user = env.user
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
