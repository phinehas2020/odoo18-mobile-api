from odoo import fields, models


class MobileAuthSession(models.Model):
    _name = "mobile.auth.session"
    _description = "Mobile Auth Session"
    _order = "id desc"

    user_id = fields.Many2one("res.users", required=True, index=True)
    device_id = fields.Char(required=True, index=True)
    device_name = fields.Char()
    refresh_token_hash = fields.Char(required=True, index=True)
    refresh_token_expires_at = fields.Datetime(required=True, index=True)
    access_jti = fields.Char(index=True)
    last_seen_at = fields.Datetime()
    revoked_at = fields.Datetime()
    company_id = fields.Many2one("res.company", index=True)

    _sql_constraints = [
        (
            "refresh_token_hash_unique",
            "unique(refresh_token_hash)",
            "Refresh token hash must be unique.",
        )
    ]
