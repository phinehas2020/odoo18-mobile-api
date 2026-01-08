import secrets

from odoo import SUPERUSER_ID, api

JWT_SECRET_PARAM = "mobile_api.jwt.secret"
JWT_ISSUER_PARAM = "mobile_api.jwt.issuer"
JWT_AUDIENCE_PARAM = "mobile_api.jwt.audience"
REFRESH_SALT_PARAM = "mobile_api.refresh_token.salt"


def _ensure_param(config, key, fallback):
    value = config.get_param(key)
    if not value:
        value = fallback
        config.set_param(key, value)
    return value


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    config = env["ir.config_parameter"].sudo()

    jwt_secret = _ensure_param(config, JWT_SECRET_PARAM, secrets.token_urlsafe(64))
    _ensure_param(config, REFRESH_SALT_PARAM, secrets.token_urlsafe(48))
    issuer = _ensure_param(config, JWT_ISSUER_PARAM, "odoo")
    audience = _ensure_param(config, JWT_AUDIENCE_PARAM, "mobile")

    validator = env.ref(
        "mobile_api_core.auth_jwt_validator_mobile", raise_if_not_found=False
    )
    if validator:
        validator.sudo().write(
            {
                "signature_type": "secret",
                "secret_key": jwt_secret,
                "secret_algorithm": "HS256",
                "issuer": issuer,
                "audience": audience,
            }
        )
