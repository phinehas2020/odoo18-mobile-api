from odoo import fields, models


class MobileChangeLogMixin(models.AbstractModel):
    _name = "mobile.change.log.mixin"
    _description = "Mobile Change Log Mixin"

    _mobile_change_log_enabled = False

    def _mobile_change_log_payload_hint(self, operation, vals=None):
        return None

    def _mobile_change_log_create_entries(self, model_name, res_ids, operation):
        if not res_ids:
            return
        now = fields.Datetime.now()
        payload_hint = self._mobile_change_log_payload_hint(operation)
        entries = [
            {
                "model": model_name,
                "res_id": res_id,
                "operation": operation,
                "write_date": now,
                "payload_hint": payload_hint,
            }
            for res_id in res_ids
        ]
        self.env["mobile.change.log"].sudo().create(entries)

    def create(self, vals_list):
        records = super().create(vals_list)
        if self._mobile_change_log_enabled:
            records._mobile_change_log_create_entries(
                records._name, records.ids, "create"
            )
        return records

    def write(self, vals):
        res = super().write(vals)
        if self._mobile_change_log_enabled:
            self._mobile_change_log_create_entries(self._name, self.ids, "write")
        return res

    def unlink(self):
        res_ids = list(self.ids)
        res = super().unlink()
        if self._mobile_change_log_enabled:
            self._mobile_change_log_create_entries(self._name, res_ids, "unlink")
        return res
