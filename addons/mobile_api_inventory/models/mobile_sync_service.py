from odoo import models

from ..services.inventory_service import MobileInventoryService


class MobileSyncService(models.AbstractModel):
    _inherit = "mobile.sync.service"

    def _handle_inventory_scan(self, device_id, action):
        service = MobileInventoryService(self.env)
        payload = action.get("payload") or {}
        return service.handle_scan(payload, device_id=device_id, event_id=action.get("event_id"))

    def _handle_inventory_validate(self, device_id, action):
        service = MobileInventoryService(self.env)
        payload = action.get("payload") or {}
        return service.handle_validate(payload, device_id=device_id, event_id=action.get("event_id"))
