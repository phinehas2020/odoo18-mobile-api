from odoo import models


class StockPicking(models.Model):
    _inherit = ["stock.picking", "mobile.change.log.mixin"]
    _mobile_change_log_enabled = True
