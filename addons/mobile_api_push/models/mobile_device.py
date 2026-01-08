from odoo import fields, models


class MobileDevice(models.Model):
    _inherit = "mobile.device"

    push_opt_out = fields.Boolean(default=False)
