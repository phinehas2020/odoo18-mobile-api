from odoo import fields, models


class MobilePushTemplate(models.Model):
    _name = "mobile.push.template"
    _description = "Mobile Push Template"
    _order = "key asc"

    key = fields.Char(required=True, index=True)
    title = fields.Char(required=True)
    body = fields.Text(required=True)
    deeplink_payload = fields.Text()
    enabled = fields.Boolean(default=True)

    _sql_constraints = [
        ("key_unique", "unique(key)", "Push template key must be unique."),
    ]
