from odoo import api, fields, models


class MobileChangeLog(models.Model):
    _name = "mobile.change.log"
    _description = "Mobile Change Log"
    _order = "seq asc"

    seq = fields.Integer(index=True, required=True)
    model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    operation = fields.Selection(
        [("create", "Create"), ("write", "Write"), ("unlink", "Unlink")],
        required=True,
    )
    write_date = fields.Datetime(index=True)
    payload_hint = fields.Char()

    @api.model
    def create(self, vals):
        if not vals.get("seq"):
            vals["seq"] = (
                self.env["ir.sequence"].sudo().next_by_code("mobile.change.log") or 0
            )
        return super().create(vals)
