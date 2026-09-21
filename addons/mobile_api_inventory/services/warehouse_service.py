import hashlib

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_round

from .inventory_service import MobileInventoryService, RecordVersionConflict


class MobileWarehouseService:
    def __init__(self, env):
        self.env = env

    def stock(self, query=None, location_id=None, limit=50):
        limit = min(max(int(limit or 50), 1), 100)
        domain = self._quant_domain(location_id) + [("quantity", "!=", 0)]
        if query:
            domain = expression.AND(
                [
                    domain,
                    [
                        "|",
                        ("product_id.name", "ilike", query),
                        ("product_id.barcode", "=", query),
                    ],
                ]
            )
        quants = self.env["stock.quant"].search(
            domain, order="product_id, location_id, lot_id", limit=limit
        )
        can_manage = self.env.user.has_group("stock.group_stock_manager")
        return {
            "items": [self._stock_item(q) for q in quants],
            "limit": limit,
            "can_adjust": can_manage,
            "can_scrap": can_manage,
        }

    def review_adjustment(self, quant_id, counted_quantity):
        self._require_stock_manager()
        quant = self._quant(quant_id)
        return self._adjustment_snapshot(quant, counted_quantity)

    def apply_adjustment(self, payload):
        self._require_stock_manager()
        if payload.get("reviewed") is not True:
            raise UserError("Review confirmation is required")
        receipt = self._receipt(payload.get("event_id"))
        quant = self._quant(payload.get("quant_id"))
        if receipt:
            self._check_receipt(receipt, "stock.quant", quant.id)
            result = self._adjustment_snapshot(quant, quant.quantity)
            result["status"] = receipt.status
            return result
        self._lock_quant(quant)
        self._check_version(self._quant_version(quant), payload.get("record_version"))
        with self.env.cr.savepoint():
            quant.inventory_quantity = payload.get("counted_quantity")
            action = quant.action_apply_inventory()
            if isinstance(action, dict):
                raise UserError("Odoo requires additional inventory adjustment review")
            self._create_receipt(payload, "success", "stock.quant", quant.id)
        result = self._adjustment_snapshot(quant, quant.quantity)
        result["status"] = "success"
        return result

    def review_scrap(self, quant_id, quantity, picking_id=None):
        self._require_stock_manager()
        quant = self._quant(quant_id)
        picking = self._optional_picking(picking_id)
        self._check_scrap_picking(quant, picking)
        destination = self._scrap_location()
        available = quant.quantity - quant.reserved_quantity
        message = None
        if quantity > available:
            message = "Requested scrap exceeds currently unreserved stock."
        return self._scrap_snapshot(
            quant, destination, quantity, picking, available, message
        )

    def apply_scrap(self, payload):
        self._require_stock_manager()
        if payload.get("reviewed") is not True:
            raise UserError("Review confirmation is required")
        quant = self._quant(payload.get("quant_id"))
        receipt = self._receipt(payload.get("event_id"))
        if receipt:
            scrap = self.env["stock.scrap"].browse(receipt.res_id)
            self._check_receipt(receipt, "stock.scrap", receipt.res_id)
            if (
                not scrap.exists()
                or scrap.product_id != quant.product_id
                or scrap.location_id != quant.location_id
                or scrap.lot_id != quant.lot_id
            ):
                raise UserError("Event ID was already used for another operation")
            return self._scrap_result(quant, scrap, receipt.status)
        self._lock_quant(quant)
        self._check_version(self._quant_version(quant), payload.get("record_version"))
        quantity = payload.get("quantity")
        available = quant.quantity - quant.reserved_quantity
        if float_compare(
            quantity,
            available,
            precision_rounding=quant.product_uom_id.rounding,
        ) > 0:
            raise UserError("Scrap quantity exceeds currently unreserved stock")
        picking = self._optional_picking(payload.get("picking_id"))
        self._check_scrap_picking(quant, picking)
        with self.env.cr.savepoint():
            scrap = self.env["stock.scrap"].create(
                {
                    "product_id": quant.product_id.id,
                    "product_uom_id": quant.product_uom_id.id,
                    "scrap_qty": quantity,
                    "location_id": quant.location_id.id,
                    "scrap_location_id": self._scrap_location().id,
                    "lot_id": quant.lot_id.id or False,
                    "package_id": quant.package_id.id or False,
                    "owner_id": quant.owner_id.id or False,
                    "picking_id": picking.id if picking else False,
                }
            )
            action = scrap.action_validate()
            if isinstance(action, dict):
                raise UserError("Odoo requires additional scrap review")
            if scrap.state != "done":
                raise UserError("Odoo did not complete the scrap")
            self._create_receipt(payload, "success", "stock.scrap", scrap.id)
        return self._scrap_result(quant, scrap, "success")

    def review_return(self, picking_id):
        self._require_stock_manager()
        picking = self._done_picking(picking_id)
        wizard = self._return_wizard(picking)
        lines = self._returnable_lines(wizard)
        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "record_version": MobileInventoryService(self.env)._record_version(picking),
            "lines": lines,
            "message": None if lines else "No quantities remain available to return.",
        }

    def apply_return(self, picking_id, payload):
        self._require_stock_manager()
        if payload.get("reviewed") is not True:
            raise UserError("Review confirmation is required")
        picking = self._done_picking(picking_id)
        receipt = self._receipt(payload.get("event_id"))
        if receipt:
            self._check_receipt(receipt, "stock.picking", receipt.res_id)
            returned = self.env["stock.picking"].browse(receipt.res_id)
            if not returned.exists() or returned.return_id != picking:
                raise UserError("Event ID was already used for another operation")
            return self._return_result(picking, returned, receipt.status)
        self._lock_picking(picking)
        current_version = MobileInventoryService(self.env)._record_version(picking)
        self._check_version(current_version, payload.get("record_version"))
        rows = payload.get("lines", [])
        move_ids = [line["move_id"] for line in rows]
        if len(move_ids) != len(set(move_ids)):
            raise UserError("Each return move may be included only once")
        requested = {line["move_id"]: line["quantity"] for line in rows}
        if not requested or all(quantity <= 0 for quantity in requested.values()):
            raise UserError("At least one positive return quantity is required")
        with self.env.cr.savepoint():
            wizard = self._return_wizard(picking)
            maximums = {line["move_id"]: line["quantity"] for line in self._returnable_lines(wizard)}
            unknown_move_ids = set(requested) - set(maximums)
            if unknown_move_ids:
                raise UserError("A selected move is not currently returnable")
            for line in wizard.product_return_moves:
                quantity = requested.get(line.move_id.id, 0)
                maximum = maximums.get(line.move_id.id, 0)
                if quantity < 0 or float_compare(
                    quantity,
                    maximum,
                    precision_rounding=line.uom_id.rounding,
                ) > 0:
                    raise UserError("Return quantity exceeds the currently returnable quantity")
                line.quantity = quantity
            action = wizard.action_create_returns()
            returned = self.env["stock.picking"].browse(action.get("res_id"))
            if not returned.exists():
                raise UserError("Odoo did not create the return transfer")
            self._create_receipt(payload, "success", "stock.picking", returned.id)
        return self._return_result(picking, returned, "success")

    def _return_wizard(self, picking):
        return self.env["stock.return.picking"].with_context(
            active_model="stock.picking", active_id=picking.id, active_ids=[picking.id]
        ).create({"picking_id": picking.id})

    def _returnable_lines(self, wizard):
        result = []
        for line in wizard.product_return_moves:
            move = line.move_id
            quantity = move.quantity
            return_moves = move.move_dest_ids.filtered(
                lambda record: record.origin_returned_move_id == move
                and record.state != "cancel"
            )
            for returned_move in return_moves:
                quantity -= (
                    returned_move.quantity
                    if returned_move.state == "done"
                    else returned_move.product_uom_qty
                )
            quantity = max(
                float_round(quantity, precision_rounding=line.uom_id.rounding), 0
            )
            if quantity:
                result.append(
                    {
                        "move_id": move.id,
                        "product_id": line.product_id.id,
                        "product_name": line.product_id.display_name,
                        "quantity": quantity,
                        "uom_name": line.uom_id.name,
                    }
                )
        return result

    def _quant_domain(self, location_id=None):
        domain = [
            ("company_id", "=", self.env.company.id),
            ("location_id.usage", "=", "internal"),
            ("location_id.scrap_location", "=", False),
        ]
        if location_id:
            domain.append(("location_id", "=", location_id))
        return domain

    def _quant(self, quant_id):
        quant = self.env["stock.quant"].browse(quant_id)
        if not quant.exists() or not quant.filtered_domain(self._quant_domain()):
            raise UserError("Stock row is not available for this company and location")
        return quant

    def _stock_item(self, quant):
        return {
            "id": quant.id,
            "product_id": quant.product_id.id,
            "product_name": quant.product_id.display_name,
            "barcode": quant.product_id.barcode or None,
            "location_id": quant.location_id.id,
            "location_name": quant.location_id.display_name,
            "lot_id": quant.lot_id.id or None,
            "lot_name": quant.lot_id.name or None,
            "quantity": quant.quantity,
            "reserved_quantity": quant.reserved_quantity,
            "uom_name": quant.product_uom_id.name,
        }

    def _adjustment_snapshot(self, quant, counted):
        return {
            "quant_id": quant.id,
            "product_id": quant.product_id.id,
            "product_name": quant.product_id.display_name,
            "location_id": quant.location_id.id,
            "location_name": quant.location_id.display_name,
            "lot_id": quant.lot_id.id or None,
            "lot_name": quant.lot_id.name or None,
            "current_quantity": quant.quantity,
            "counted_quantity": counted,
            "difference": counted - quant.quantity,
            "record_version": self._quant_version(quant),
            "reviewed": True,
            "message": None,
        }

    def _scrap_snapshot(self, quant, destination, quantity, picking, available, message):
        return {
            "quant_id": quant.id,
            "product_id": quant.product_id.id,
            "product_name": quant.product_id.display_name,
            "source_location_id": quant.location_id.id,
            "source_location_name": quant.location_id.display_name,
            "scrap_location_id": destination.id,
            "scrap_location_name": destination.display_name,
            "lot_id": quant.lot_id.id or None,
            "lot_name": quant.lot_id.name or None,
            "available_quantity": available,
            "scrap_quantity": quantity,
            "record_version": self._quant_version(quant),
            "reviewed": True,
            "message": message,
        }

    def _scrap_result(self, quant, scrap, status):
        result = self._scrap_snapshot(
            quant,
            scrap.scrap_location_id,
            scrap.scrap_qty,
            scrap.picking_id,
            quant.quantity - quant.reserved_quantity,
            None,
        )
        result.update({"status": status, "scrap_id": scrap.id, "state": scrap.state})
        return result

    def _return_result(self, original, returned, status):
        return {
            "status": status,
            "original_picking_id": original.id,
            "new_picking_id": returned.id,
            "new_picking_name": returned.name,
            "state": returned.state,
        }

    def _quant_version(self, quant):
        values = [
            str(quant.id),
            quant.write_date.isoformat() if quant.write_date else "",
            repr(quant.quantity),
            repr(quant.reserved_quantity),
            str(quant.lot_id.id or 0),
        ]
        return hashlib.sha256("\x1f".join(values).encode()).hexdigest()

    def _lock_quant(self, quant):
        self.env.cr.execute("SELECT id FROM stock_quant WHERE id = %s FOR UPDATE", [quant.id])
        quant.invalidate_recordset(
            ["write_date", "quantity", "reserved_quantity", "lot_id"]
        )

    def _lock_picking(self, picking):
        self.env.cr.execute("SELECT id FROM stock_picking WHERE id = %s FOR UPDATE", [picking.id])
        picking.invalidate_recordset(["write_date", "state", "move_ids", "move_line_ids"])

    def _check_version(self, current, supplied):
        if not supplied or current != supplied:
            raise RecordVersionConflict(current)

    def _require_stock_manager(self):
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError("Inventory manager access is required")

    def _scrap_location(self):
        location = self.env["stock.location"].search(
            [
                ("company_id", "in", [False, self.env.company.id]),
                ("scrap_location", "=", True),
            ],
            limit=1,
        )
        if not location:
            raise UserError("No scrap location is configured")
        return location

    def _optional_picking(self, picking_id):
        if not picking_id:
            return self.env["stock.picking"]
        picking = self.env["stock.picking"].browse(picking_id)
        if not picking.exists() or picking.company_id != self.env.company:
            raise UserError("Picking not found")
        return picking

    def _done_picking(self, picking_id):
        picking = self._optional_picking(picking_id)
        if not picking or picking.state != "done":
            raise UserError("Only completed transfers can be returned")
        return picking

    def _check_scrap_picking(self, quant, picking):
        if not picking:
            return
        expected_location = (
            picking.location_dest_id if picking.state == "done" else picking.location_id
        )
        if quant.location_id != expected_location or quant.product_id not in picking.move_ids.product_id:
            raise UserError("Stock row does not belong to the selected transfer context")

    def _receipt(self, event_id):
        if not event_id:
            return None
        return self.env["mobile.outbox.receipt"].sudo().search(
            [("event_id", "=", event_id)], limit=1
        )

    def _check_receipt(self, receipt, model, res_id):
        if receipt.model != model or receipt.res_id != res_id:
            raise UserError("Event ID was already used for another operation")

    def _create_receipt(self, payload, status, model, res_id, message=None):
        return self.env["mobile.outbox.receipt"].sudo().create(
            {
                "device_id": payload.get("device_id"),
                "event_id": payload.get("event_id"),
                "processed_at": fields.Datetime.now(),
                "status": status,
                "message": message,
                "model": model,
                "res_id": res_id,
            }
        )
