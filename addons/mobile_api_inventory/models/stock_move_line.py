from odoo import models


class MobileStockMoveLine(models.Model):
    _inherit = ["stock.move.line", "mobile.change.log.mixin"]
    _mobile_change_log_enabled = True
