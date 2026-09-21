import hashlib
import logging

from odoo import fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RecordVersionConflict(UserError):
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
        receipt = self._get_receipt(event_id)
        if receipt:
            if (
                receipt.status == "success"
                and (
                    receipt.model != "stock.move.line"
                    or receipt.res_id not in picking.move_line_ids.ids
                )
            ):
                raise UserError("Event ID was already used for another operation")
            warnings = [receipt.message] if receipt.message else []
            _logger.info("mobile_api.inventory.scan.idempotent user_id=%s picking_id=%s event_id=%s status=%s", self.env.user.id, picking_id, event_id, receipt.status)
            return self._scan_response(event_id, picking, receipt.status, warnings)
        if picking.state in ("done", "cancel"):
            raise UserError("Completed or cancelled transfers cannot be scanned")
        record_version = payload.get("record_version")
        self._check_record_version(picking, record_version)
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
        if len(line) > 1:
            raise UserError(
                "Multiple move lines match this product; update the intended quantity and lot explicitly"
            )
        line = line[0]
        qty = payload.get("qty") if payload.get("qty") is not None else 1.0
        if qty <= 0:
            raise UserError("Scan quantity must be greater than zero")
        new_quantity = self._line_done_qty(line) + qty
        if line.product_id.tracking != "none" and not (line.lot_id or line.lot_name):
            raise UserError(
                "Tracked products require explicit quantity and lot or serial entry"
            )
        if line.product_id.tracking == "serial" and new_quantity > 1:
            raise UserError("A serial-tracked move line cannot exceed one unit")
        line.write({self._done_quantity_field(): new_quantity})
        self._create_receipt(event_id, device_id, "success", "stock.move.line", line.id)
        _logger.info("mobile_api.inventory.scan.success user_id=%s picking_id=%s line_id=%s product_id=%s qty=%s event_id=%s", self.env.user.id, picking_id, line.id, product.id, qty, event_id)
        return self._scan_response(event_id, picking, "success")

    def update_line(self, picking_id, line_id, payload, device_id, event_id=None):
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            raise UserError("Picking not found")
        line = picking.move_line_ids.filtered(lambda record: record.id == line_id)
        if not line:
            raise UserError("Move line does not belong to this picking")
        line = line[0]
        receipt = self._get_receipt(event_id)
        if receipt:
            if receipt.model != "stock.move.line" or receipt.res_id != line.id:
                raise UserError("Event ID was already used for another operation")
            return self._line_update_response(picking, line, receipt.status)
        if picking.state in ("done", "cancel"):
            raise UserError("Completed or cancelled transfers cannot be edited")
        self._check_record_version(picking, payload.get("record_version"))
        quantity = payload.get("qty_done")
        if quantity is None or quantity < 0:
            raise UserError("Done quantity must be zero or greater")

        values = {self._done_quantity_field(): quantity}
        self._prepare_lot_values(picking, line, payload, quantity, values)
        line.write(values)
        self._create_receipt(event_id, device_id, "success", "stock.move.line", line.id)
        return self._line_update_response(picking, line, "success")

    def create_line(self, picking_id, payload, device_id, event_id=None):
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists():
            raise UserError("Picking not found")
        receipt = self._get_receipt(event_id)
        if receipt:
            line = self.env["stock.move.line"].browse(receipt.res_id)
            if (
                receipt.model != "stock.move.line"
                or not line.exists()
                or line.picking_id != picking
            ):
                raise UserError("Event ID was already used for another operation")
            return self._line_update_response(picking, line, receipt.status)
        if picking.state in ("done", "cancel"):
            raise UserError("Completed or cancelled transfers cannot be edited")
        self._check_record_version(picking, payload.get("record_version"))
        move = picking.move_ids.filtered(lambda record: record.id == payload.get("move_id"))
        if not move:
            raise UserError("Stock move does not belong to this picking")
        move = move[0]
        quantity = payload.get("qty_done")
        if quantity is None or quantity < 0:
            raise UserError("Done quantity must be zero or greater")
        with self.env.cr.savepoint():
            line = self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    self._done_quantity_field(): 0,
                }
            )
            values = {self._done_quantity_field(): quantity}
            self._prepare_lot_values(picking, line, payload, quantity, values)
            line.write(values)
            self._create_receipt(
                event_id, device_id, "success", "stock.move.line", line.id
            )
        return self._line_update_response(picking, line, "success")

    def _prepare_lot_values(self, picking, line, payload, quantity, values):
        lot_id = payload.get("lot_id")
        lot_name = (payload.get("lot_name") or "").strip() or None
        if lot_id and lot_name:
            raise UserError("Provide either lot_id or lot_name, not both")
        tracking = line.product_id.tracking
        if tracking == "serial" and quantity not in (0, 1):
            raise UserError("Serial-tracked move lines must have a quantity of zero or one")
        if tracking == "none":
            if lot_id or lot_name:
                raise UserError("This product does not use lot or serial tracking")
            return
        if lot_id:
            lot = self.env["stock.lot"].browse(lot_id)
            if not lot.exists() or lot.product_id != line.product_id:
                raise UserError("Lot or serial number does not match this product")
            if lot.company_id and lot.company_id != picking.company_id:
                raise UserError("Lot or serial number belongs to another company")
            if not picking.picking_type_id.use_existing_lots:
                raise UserError("This operation type does not permit existing lots")
            values.update({"lot_id": lot.id, "lot_name": False})
            return
        if lot_name:
            existing_lot = self.env["stock.lot"].search(
                [
                    ("name", "=", lot_name),
                    ("product_id", "=", line.product_id.id),
                    ("company_id", "in", [False, picking.company_id.id]),
                ],
                limit=1,
            )
            if existing_lot:
                if not picking.picking_type_id.use_existing_lots:
                    raise UserError("This operation type does not permit existing lots")
                values.update({"lot_id": existing_lot.id, "lot_name": False})
            elif (
                picking.picking_type_id.code == "incoming"
                and picking.picking_type_id.use_create_lots
            ):
                values.update({"lot_id": False, "lot_name": lot_name})
            else:
                raise UserError("A new lot or serial number is only allowed on receipts")
            return
        if quantity and not (line.lot_id or line.lot_name):
            raise UserError("A lot or serial number is required for this product")

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
        receipt = self._get_receipt(event_id)
        if receipt:
            if receipt.model != "stock.picking" or receipt.res_id != picking.id:
                raise UserError("Event ID was already used for another operation")
            _logger.info("mobile_api.inventory.validate.idempotent user_id=%s picking_id=%s event_id=%s status=%s", self.env.user.id, picking_id, event_id, receipt.status)
            return self._validate_response(picking, receipt.status, receipt.message)
        record_version = payload.get("record_version")
        self._check_record_version(picking, record_version)
        if picking.state == "done":
            self._create_receipt(event_id, device_id, "success", "stock.picking", picking.id)
            return self._validate_response(picking, "success")
        try:
            action = picking.button_validate()
            if self._is_backorder_action(action):
                policy = payload.get("backorder_policy") or "ask"
                if policy == "ask":
                    return self._validate_response(
                        picking,
                        "needs_backorder",
                        "Choose whether to create or cancel the remaining backorder.",
                        backorder_required=True,
                    )
                wizard = self.env["stock.backorder.confirmation"].with_context(
                    **action.get("context", {})
                ).create(
                    {
                        "pick_ids": [(6, 0, [picking.id])],
                        "backorder_confirmation_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "picking_id": picking.id,
                                    "to_backorder": policy == "create",
                                },
                            )
                        ],
                    }
                )
                if policy == "create":
                    wizard.process()
                elif policy == "cancel":
                    wizard.process_cancel_backorder()
                else:
                    raise UserError("Invalid backorder policy")
        except UserError as exc:
            _logger.warning("mobile_api.inventory.validate.user_error user_id=%s picking_id=%s event_id=%s message=%s", self.env.user.id, picking_id, event_id, str(exc))
            self._create_receipt(event_id, device_id, "failed", "stock.picking", picking.id, str(exc))
            return {
                "event_id": event_id,
                "status": "failed",
                "message": str(exc),
            }
        if picking.state != "done":
            message = "Odoo did not complete the transfer"
            self._create_receipt(event_id, device_id, "failed", "stock.picking", picking.id, message)
            return self._validate_response(picking, "failed", message)
        backorder = self.env["stock.picking"].search(
            [("backorder_id", "=", picking.id), ("state", "!=", "cancel")],
            order="id desc",
            limit=1,
        )
        self._create_receipt(event_id, device_id, "success", "stock.picking", picking.id)
        _logger.info("mobile_api.inventory.validate.success user_id=%s picking_id=%s event_id=%s", self.env.user.id, picking_id, event_id)
        return self._validate_response(
            picking,
            "success",
            backorder_picking_id=backorder.id if backorder else None,
        )

    def _is_backorder_action(self, action):
        return isinstance(action, dict) and action.get("res_model") == "stock.backorder.confirmation"

    def _validate_response(
        self,
        picking,
        status,
        message=None,
        backorder_required=False,
        backorder_picking_id=None,
    ):
        return {
            "status": status,
            "picking_state": picking.state,
            "record_version": self._record_version(picking),
            "backorder_required": backorder_required,
            "backorder_picking_id": backorder_picking_id,
            "message": message,
        }

    def _check_record_version(self, picking, record_version):
        if not record_version:
            return
        server_version = self._record_version(picking)
        if server_version != record_version:
            _logger.warning("mobile_api.inventory.record_version.conflict picking_id=%s client=%s server=%s", picking.id, record_version, server_version)
            raise RecordVersionConflict(server_version)

    def _record_version(self, picking):
        parts = [
            str(picking.id),
            picking.state or "",
            picking.write_date.isoformat() if picking.write_date else "",
        ]
        for move in picking.move_ids.sorted("id"):
            parts.extend(
                [
                    str(move.id),
                    move.write_date.isoformat() if move.write_date else "",
                    str(move.product_id.id),
                    repr(move.product_uom_qty),
                    move.state or "",
                ]
            )
        for line in picking.move_line_ids.sorted("id"):
            parts.extend(
                [
                    str(line.id),
                    line.write_date.isoformat() if line.write_date else "",
                    repr(self._line_done_qty(line)),
                    str(line.lot_id.id or 0),
                    line.lot_name or "",
                ]
            )
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    def _scan_response(self, event_id, picking, status, warnings=None):
        return {
            "event_id": event_id,
            "status": status,
            "updated_lines": [self._picking_line(line) for line in picking.move_line_ids],
            "warnings": warnings or [],
            "next_expected": None,
            "record_version": self._record_version(picking),
        }

    def _line_update_response(self, picking, line, status):
        return {
            "status": status,
            "line": self._picking_line(line),
            "record_version": self._record_version(picking),
            "warnings": [],
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
            "picking_type_code": picking.picking_type_id.code,
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
            "picking_type_code": picking.picking_type_id.code,
            "scheduled_date": picking.scheduled_date,
            "priority": picking.priority,
            "partner_name": picking.partner_id.display_name if picking.partner_id else None,
            "source_location": self._location_info(picking.location_id),
            "dest_location": self._location_info(picking.location_dest_id),
            "record_version": self._record_version(picking),
            "moves": [self._picking_move(move) for move in picking.move_ids],
            "lines": [self._picking_line(line) for line in picking.move_line_ids],
        }

    def _picking_move(self, move):
        return {
            "id": move.id,
            "product_id": move.product_id.id,
            "product_name": move.product_id.display_name,
            "barcode": move.product_id.barcode or None,
            "qty_demanded": move.product_uom_qty,
            "qty_done": sum(self._line_done_qty(line) for line in move.move_line_ids),
            "uom_name": move.product_uom.name if move.product_uom else None,
            "tracking": move.product_id.tracking,
        }

    def _picking_line(self, line):
        qty_reserved = getattr(line, "reserved_uom_qty", 0.0)
        qty_demanded = getattr(line.move_id, "product_uom_qty", 0.0)
        return {
            "id": line.id,
            "move_id": line.move_id.id,
            "product_id": line.product_id.id,
            "product_name": line.product_id.display_name,
            "barcode": line.product_id.barcode or None,
            "qty_done": self._line_done_qty(line),
            "qty_reserved": qty_reserved,
            "qty_demanded": qty_demanded,
            "uom_name": line.product_uom_id.name if line.product_uom_id else None,
            "lot_id": line.lot_id.id if line.lot_id else None,
            "lot_name": line.lot_id.name if line.lot_id else (line.lot_name or None),
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
            "barcode": getattr(location, "barcode", None) or None,
        }
