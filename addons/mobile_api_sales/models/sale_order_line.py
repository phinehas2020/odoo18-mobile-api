from odoo import models


class SaleOrderLine(models.Model):
    _inherit = ["sale.order.line", "mobile.change.log.mixin"]
    _mobile_change_log_enabled = True
