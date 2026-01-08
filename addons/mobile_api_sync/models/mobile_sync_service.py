from odoo import api, fields, models


class MobileSyncService(models.AbstractModel):
    _name = "mobile.sync.service"
    _description = "Mobile Sync Service"

    @api.model
    def get_bootstrap_reference(self, user):
        return {
            "user_id": user.id,
            "company_id": user.company_id.id if user.company_id else None,
            "timestamp": fields.Datetime.now(),
            "warehouses": [],
            "picking_types": [],
            "products": [],
        }

    @api.model
    def current_cursor(self):
        last = self.env["mobile.change.log"].sudo().search([], order="seq desc", limit=1)
        return last.seq if last else 0

    @api.model
    def get_changes(self, cursor, models_filter=None):
        domain = [("seq", ">", cursor or 0)]
        if models_filter:
            domain.append(("model", "in", models_filter))
        changes = self.env["mobile.change.log"].sudo().search(domain, order="seq asc")
        new_cursor = cursor or 0
        payload = []
        for change in changes:
            new_cursor = max(new_cursor, change.seq)
            payload.append(
                {
                    "seq": change.seq,
                    "model": change.model,
                    "res_id": change.res_id,
                    "operation": change.operation,
                    "write_date": change.write_date,
                    "payload_hint": change.payload_hint,
                }
            )
        return payload, new_cursor

    @api.model
    def handle_actions(self, device_id, actions):
        results = []
        for action in actions:
            event_id = action.get("event_id")
            receipt = (
                self.env["mobile.outbox.receipt"]
                .sudo()
                .search([("event_id", "=", event_id)], limit=1)
            )
            if receipt and not receipt.retry_requested:
                results.append(
                    {
                        "event_id": event_id,
                        "status": receipt.status,
                        "message": receipt.message,
                        "model": receipt.model,
                        "res_id": receipt.res_id,
                    }
                )
                continue
            result = self._dispatch_action(device_id, action)
            values = {
                "device_id": device_id,
                "event_id": event_id,
                "processed_at": fields.Datetime.now(),
                "status": result.get("status", "failed"),
                "message": result.get("message"),
                "model": result.get("model"),
                "res_id": result.get("res_id"),
                "retry_requested": False,
            }
            if receipt:
                receipt.write(values)
            else:
                self.env["mobile.outbox.receipt"].sudo().create(values)
            results.append(result)
        return results

    def _dispatch_action(self, device_id, action):
        action_type = (action.get("type") or "").replace(".", "_")
        handler = getattr(self, f"_handle_{action_type}", None)
        if handler:
            return handler(device_id, action)
        return {
            "event_id": action.get("event_id"),
            "status": "failed",
            "message": "Unsupported action",
        }
