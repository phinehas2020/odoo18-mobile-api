from odoo import models


class StockMoveLine(models.Model):
    _inherit = ["stock.move.line", "mobile.change.log.mixin"]
    _mobile_change_log_enabled = True
