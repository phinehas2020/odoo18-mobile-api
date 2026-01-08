from odoo import fields, models


class MobileLoginAttempt(models.Model):
    _name = "mobile.auth.login.attempt"
    _description = "Mobile Auth Login Attempt"
    _order = "id desc"

    login = fields.Char(index=True)
    ip_address = fields.Char(index=True)
    device_id = fields.Char(index=True)
    attempted_at = fields.Datetime(default=fields.Datetime.now, index=True)
    success = fields.Boolean(default=False)
