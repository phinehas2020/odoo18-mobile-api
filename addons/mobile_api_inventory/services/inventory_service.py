from odoo import fields
from odoo.exceptions import UserError


class RecordVersionConflict(Exception):
    def __init__(self, server_version):
        super().__init__("Record version conflict")
        self.server_version = server_version


class MobileInventoryService:
    def __init__(self, env):
        self.env = env

    def list_pickings(self, state=None, mine=False, updated_since=None):
        domain = []
        if state:
            domain.append(("state", "in", state))
        if mine:
            domain.append(("user_id", "=", self.env.user.id))
        if updated_since:
            domain.append(("write_date", ">=", updated_since))
        pickings = self.env["stock.picking"].search(domain, order="write_date desc")
        return [self._picking_list_item(picking) for picking in pickings]

    def get_picking_detail(self, picking_id):
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            return None
        return self._picking_detail(picking)

    def resolve_barcode(self, code):
        product = self.env["product.product"].search([("barcode", "=", code)], limit=1)
        if product:
            return {
                "match_type": "product",
                "id": product.id,
                "name": product.display_name,
                "actions": [{"action": "add_to_picking", "label": "Scan product"}],
            }
        location = self.env["stock.location"].search(
            [("barcode", "=", code)], limit=1
        )
        if location:
            return {
                "match_type": "location",
                "id": location.id,
                "name": location.display_name,
                "actions": [{"action": "set_location", "label": "Use location"}],
            }
        lot = self.env["stock.lot"].search(
            ["|", ("name", "=", code), ("barcode", "=", code)], limit=1
        )
        if lot:
            return {
                "match_type": "lot",
                "id": lot.id,
                "name": lot.display_name,
                "actions": [{"action": "set_lot", "label": "Use lot"}],
            }
        picking = self.env["stock.picking"].search([("name", "=", code)], limit=1)
        if picking:
            return {
                "match_type": "picking",
                "id": picking.id,
                "name": picking.name,
                "actions": [{"action": "open_picking", "label": "Open picking"}],
            }
        return None

    def handle_scan(self, payload, device_id, event_id=None):
        picking_id = payload.get("picking_id") or payload.get("id")
        if not picking_id:
            return {
                "event_id": event_id,
                "status": "failed",
                "message": "Missing picking id",
            }
        return self.scan(picking_id, payload, device_id, event_id)

    def handle_validate(self, payload, device_id, event_id=None):
        picking_id = payload.get("picking_id") or payload.get("id")
        if not picking_id:
            return {
                "event_id": event_id,
                "status": "failed",
                "message": "Missing picking id",
            }
        return self.validate(picking_id, payload, device_id, event_id)

    def scan(self, picking_id, payload, device_id, event_id=None):
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            return {
                "event_id": event_id,
                "status": "failed",
                "message": "Picking not found",
            }
        record_version = payload.get("record_version")
        self._check_record_version(picking, record_version)
        receipt = self._get_receipt(event_id)
        if receipt:
            warnings = [receipt.message] if receipt.message else []
            return self._scan_response(event_id, picking, receipt.status, warnings)
        code = payload.get("code")
        if not code:
            message = "Missing code"
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        product = self.env["product.product"].search([("barcode", "=", code)], limit=1)
        if not product:
            message = "Unknown barcode"
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        line = picking.move_line_ids.filtered(lambda l: l.product_id.id == product.id)
        if not line:
            message = "No matching line"
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        line = line[0]
        qty = payload.get("qty") or 1.0
        line.write({"qty_done": line.qty_done + qty})
        self._create_receipt(event_id, device_id, "success", "stock.move.line", line.id)
        return self._scan_response(event_id, picking, "success")

    def validate(self, picking_id, payload, device_id, event_id=None):
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            return {
                "event_id": event_id,
                "status": "failed",
                "message": "Picking not found",
            }
        record_version = payload.get("record_version")
        self._check_record_version(picking, record_version)
        receipt = self._get_receipt(event_id)
        if receipt:
            return {
                "event_id": event_id,
                "status": receipt.status,
                "message": receipt.message,
                "model": receipt.model,
                "res_id": receipt.res_id,
            }
        try:
            picking.button_validate()
        except UserError as exc:
            self._create_receipt(event_id, device_id, "failed", "stock.picking", picking.id, str(exc))
            return {
                "event_id": event_id,
                "status": "failed",
                "message": str(exc),
            }
        self._create_receipt(event_id, device_id, "success", "stock.picking", picking.id)
        return {
            "event_id": event_id,
            "status": "success",
            "model": "stock.picking",
            "res_id": picking.id,
        }

    def _check_record_version(self, picking, record_version):
        if not record_version:
            return
        server_version = self._record_version(picking)
        if server_version != record_version:
            raise RecordVersionConflict(server_version)

    def _record_version(self, picking):
        return picking.write_date.isoformat() if picking.write_date else None

    def _scan_response(self, event_id, picking, status, warnings=None):
        return {
            "event_id": event_id,
            "status": status,
            "updated_lines": [self._picking_line(line) for line in picking.move_line_ids],
            "warnings": warnings or [],
            "next_expected": None,
        }

    def _get_receipt(self, event_id):
        if not event_id:
            return None
        return (
            self.env["mobile.outbox.receipt"]
            .sudo()
            .search([("event_id", "=", event_id)], limit=1)
        )

    def _create_receipt(self, event_id, device_id, status, model, res_id, message=None):
        if not event_id:
            return None
        return (
            self.env["mobile.outbox.receipt"]
            .sudo()
            .create(
                {
                    "device_id": device_id,
                    "event_id": event_id,
                    "processed_at": fields.Datetime.now(),
                    "status": status,
                    "message": message,
                    "model": model,
                    "res_id": res_id,
                }
            )
        )

    def _picking_list_item(self, picking):
        progress = self._picking_progress(picking)
        return {
            "id": picking.id,
            "name": picking.name,
            "picking_type": picking.picking_type_id.display_name,
            "scheduled_date": picking.scheduled_date,
            "priority": picking.priority,
            "partner_name": picking.partner_id.display_name if picking.partner_id else None,
            "progress": progress,
        }

    def _picking_detail(self, picking):
        return {
            "id": picking.id,
            "name": picking.name,
            "state": picking.state,
            "picking_type": picking.picking_type_id.display_name,
            "scheduled_date": picking.scheduled_date,
            "priority": picking.priority,
            "partner_name": picking.partner_id.display_name if picking.partner_id else None,
            "source_location": self._location_info(picking.location_id),
            "dest_location": self._location_info(picking.location_dest_id),
            "record_version": self._record_version(picking),
            "lines": [self._picking_line(line) for line in picking.move_line_ids],
        }

    def _picking_line(self, line):
        qty_reserved = getattr(line, "reserved_uom_qty", 0.0)
        qty_demanded = getattr(line.move_id, "product_uom_qty", 0.0)
        return {
            "id": line.id,
            "product_id": line.product_id.id,
            "product_name": line.product_id.display_name,
            "barcode": line.product_id.barcode,
            "qty_done": line.qty_done,
            "qty_reserved": qty_reserved,
            "qty_demanded": qty_demanded,
            "uom_name": line.product_uom_id.name if line.product_uom_id else None,
            "lot_name": line.lot_id.name if line.lot_id else None,
            "tracking": line.product_id.tracking,
        }

    def _picking_progress(self, picking):
        total = 0.0
        done = 0.0
        for line in picking.move_line_ids:
            total += getattr(line.move_id, "product_uom_qty", 0.0)
            done += line.qty_done
        return {"done": done, "total": total}

    def _location_info(self, location):
        return {
            "id": location.id,
            "name": location.display_name,
            "barcode": getattr(location, "barcode", None),
        }
