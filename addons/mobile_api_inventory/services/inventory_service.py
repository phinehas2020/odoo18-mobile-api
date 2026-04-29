import logging

from odoo import fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RecordVersionConflict(Exception):
    def __init__(self, server_version):
        super().__init__("Record version conflict")
        self.server_version = server_version


class MobileInventoryService:
    def __init__(self, env):
        self.env = env

    def list_pickings(self, state=None, mine=False, updated_since=None):
        _logger.info(
            "mobile_api.inventory.list_pickings.start user_id=%s state=%s mine=%s updated_since=%s",
            self.env.user.id,
            state,
            mine,
            updated_since,
        )
        domain = []
        if state:
            domain.append(("state", "in", state))
        if mine:
            domain.append(("user_id", "=", self.env.user.id))
        if updated_since:
            domain.append(("write_date", ">=", updated_since))
        pickings = self.env["stock.picking"].search(domain, order="write_date desc")
        _logger.info(
            "mobile_api.inventory.list_pickings.success user_id=%s count=%s domain=%s",
            self.env.user.id,
            len(pickings),
            domain,
        )
        return [self._picking_list_item(picking) for picking in pickings]

    def get_picking_detail(self, picking_id):
        _logger.info("mobile_api.inventory.get_picking_detail.start user_id=%s picking_id=%s", self.env.user.id, picking_id)
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            _logger.warning("mobile_api.inventory.get_picking_detail.not_found user_id=%s picking_id=%s", self.env.user.id, picking_id)
            return None
        _logger.info(
            "mobile_api.inventory.get_picking_detail.success user_id=%s picking_id=%s state=%s lines=%s",
            self.env.user.id,
            picking_id,
            picking.state,
            len(picking.move_line_ids),
        )
        return self._picking_detail(picking)

    def resolve_barcode(self, code):
        _logger.info("mobile_api.inventory.resolve_barcode.start user_id=%s code_hash=%s", self.env.user.id, hash(code))
        product = self.env["product.product"].search([("barcode", "=", code)], limit=1)
        if product:
            _logger.info("mobile_api.inventory.resolve_barcode.product user_id=%s product_id=%s", self.env.user.id, product.id)
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
            _logger.info("mobile_api.inventory.resolve_barcode.location user_id=%s location_id=%s", self.env.user.id, location.id)
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
            _logger.info("mobile_api.inventory.resolve_barcode.lot user_id=%s lot_id=%s", self.env.user.id, lot.id)
            return {
                "match_type": "lot",
                "id": lot.id,
                "name": lot.display_name,
                "actions": [{"action": "set_lot", "label": "Use lot"}],
            }
        picking = self.env["stock.picking"].search([("name", "=", code)], limit=1)
        if picking:
            _logger.info("mobile_api.inventory.resolve_barcode.picking user_id=%s picking_id=%s", self.env.user.id, picking.id)
            return {
                "match_type": "picking",
                "id": picking.id,
                "name": picking.name,
                "actions": [{"action": "open_picking", "label": "Open picking"}],
            }
        _logger.info("mobile_api.inventory.resolve_barcode.not_found user_id=%s code_hash=%s", self.env.user.id, hash(code))
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
        _logger.info(
            "mobile_api.inventory.scan.start user_id=%s picking_id=%s device_id=%s event_id=%s code_present=%s",
            self.env.user.id,
            picking_id,
            device_id,
            event_id,
            bool(payload.get("code")),
        )
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            _logger.warning("mobile_api.inventory.scan.not_found user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
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
            _logger.info("mobile_api.inventory.scan.idempotent user_id=%s picking_id=%s event_id=%s status=%s", self.env.user.id, picking_id, event_id, receipt.status)
            return self._scan_response(event_id, picking, receipt.status, warnings)
        code = payload.get("code")
        if not code:
            message = "Missing code"
            _logger.warning("mobile_api.inventory.scan.missing_code user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        product = self.env["product.product"].search([("barcode", "=", code)], limit=1)
        if not product:
            message = "Unknown barcode"
            _logger.warning("mobile_api.inventory.scan.unknown_barcode user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        line = picking.move_line_ids.filtered(lambda l: l.product_id.id == product.id)
        if not line:
            message = "No matching line"
            _logger.warning("mobile_api.inventory.scan.no_matching_line user_id=%s picking_id=%s product_id=%s event_id=%s", self.env.user.id, picking_id, product.id, event_id)
            self._create_receipt(event_id, device_id, "failed", "stock.move.line", None, message)
            return self._scan_response(event_id, picking, "failed", [message])
        line = line[0]
        qty = payload.get("qty") or 1.0
        line.write({self._done_quantity_field(): self._line_done_qty(line) + qty})
        self._create_receipt(event_id, device_id, "success", "stock.move.line", line.id)
        _logger.info("mobile_api.inventory.scan.success user_id=%s picking_id=%s line_id=%s product_id=%s qty=%s event_id=%s", self.env.user.id, picking_id, line.id, product.id, qty, event_id)
        return self._scan_response(event_id, picking, "success")

    def validate(self, picking_id, payload, device_id, event_id=None):
        _logger.info("mobile_api.inventory.validate.start user_id=%s picking_id=%s device_id=%s event_id=%s", self.env.user.id, picking_id, device_id, event_id)
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            _logger.warning("mobile_api.inventory.validate.not_found user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
            return {
                "event_id": event_id,
                "status": "failed",
                "message": "Picking not found",
            }
        record_version = payload.get("record_version")
        self._check_record_version(picking, record_version)
        receipt = self._get_receipt(event_id)
        if receipt:
            _logger.info("mobile_api.inventory.validate.idempotent user_id=%s picking_id=%s event_id=%s status=%s", self.env.user.id, picking_id, event_id, receipt.status)
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
            _logger.warning("mobile_api.inventory.validate.user_error user_id=%s picking_id=%s event_id=%s message=%s", self.env.user.id, picking_id, event_id, str(exc))
            self._create_receipt(event_id, device_id, "failed", "stock.picking", picking.id, str(exc))
            return {
                "event_id": event_id,
                "status": "failed",
                "message": str(exc),
            }
        self._create_receipt(event_id, device_id, "success", "stock.picking", picking.id)
        _logger.info("mobile_api.inventory.validate.success user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
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
            _logger.warning("mobile_api.inventory.record_version.conflict picking_id=%s client=%s server=%s", picking.id, record_version, server_version)
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
            "qty_done": self._line_done_qty(line),
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
            done += self._line_done_qty(line)
        return {"done": done, "total": total}

    def _done_quantity_field(self):
        move_line_fields = self.env["stock.move.line"]._fields
        for field_name in ("qty_done", "quantity_done", "quantity"):
            if field_name in move_line_fields:
                return field_name
        raise AttributeError("stock.move.line has no done quantity field")

    def _line_done_qty(self, line):
        return getattr(line, self._done_quantity_field(), 0.0) or 0.0

    def _location_info(self, location):
        return {
            "id": location.id,
            "name": location.display_name,
            "barcode": getattr(location, "barcode", None),
        }
