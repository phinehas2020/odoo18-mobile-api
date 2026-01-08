from odoo import fields, models


class MobileOutboxReceipt(models.Model):
    _name = "mobile.outbox.receipt"
    _description = "Mobile Outbox Receipt"
    _order = "id desc"

    device_id = fields.Char(required=True, index=True)
    event_id = fields.Char(required=True, index=True)
    processed_at = fields.Datetime()
    status = fields.Selection(
        [("success", "Success"), ("failed", "Failed")], default="success"
    )
    message = fields.Char()
    model = fields.Char(index=True)
    res_id = fields.Integer(index=True)
    retry_requested = fields.Boolean(default=False)

    _sql_constraints = [
        ("event_id_unique", "unique(event_id)", "Event ID must be unique."),
    ]

    def action_retry(self):
        self.write({"retry_requested": True})
        return True
