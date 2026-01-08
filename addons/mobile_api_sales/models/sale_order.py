from odoo import models


class SaleOrder(models.Model):
    _inherit = ["sale.order", "mobile.change.log.mixin"]
    _mobile_change_log_enabled = True
