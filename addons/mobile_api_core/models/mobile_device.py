from odoo import fields, models


class MobileDevice(models.Model):
    _name = "mobile.device"
    _description = "Mobile Device"
    _order = "last_seen_at desc"

    user_id = fields.Many2one("res.users", required=True, index=True)
    device_id = fields.Char(required=True, index=True)
    device_name = fields.Char()
    platform = fields.Selection([("ios", "iOS")], default="ios", required=True)
    model = fields.Char()
    os_version = fields.Char()
    app_version = fields.Char()
    push_token = fields.Char()
    last_seen_at = fields.Datetime()
    revoked_at = fields.Datetime()

    _sql_constraints = [
        ("device_id_unique", "unique(device_id)", "Device ID must be unique."),
    ]
