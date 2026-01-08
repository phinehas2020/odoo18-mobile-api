from odoo import fields, models


class AuthJwtValidator(models.Model):
    _inherit = "auth.jwt.validator"

    user_id_strategy = fields.Selection(
        selection_add=[("payload_uid", "Payload UID")],
        ondelete={"payload_uid": "cascade"},
    )
    partner_id_strategy = fields.Selection(
        selection_add=[("payload_partner_id", "Payload partner id")],
        ondelete={"payload_partner_id": "cascade"},
    )

    def _get_uid(self, payload):
        if self.user_id_strategy == "payload_uid":
            value = payload.get("uid") or payload.get("user_id") or payload.get("sub")
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return super()._get_uid(payload)

    def _get_partner_id(self, payload):
        if self.partner_id_strategy == "payload_partner_id":
            value = payload.get("partner_id")
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return super()._get_partner_id(payload)
