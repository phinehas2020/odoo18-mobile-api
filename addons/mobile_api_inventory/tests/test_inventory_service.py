from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.base.tests.common import BaseCommon

from ..services.inventory_service import MobileInventoryService


@tagged("post_install", "-at_install")
class TestInventoryService(BaseCommon):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create(
            {"name": "Test Product", "barcode": "ABC123"}
        )
        picking_type = self.env.ref("stock.picking_type_out")
        self.picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": "Move",
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "product_uom": self.product.uom_id.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "picking_id": self.picking.id,
            }
        )
        line_values = {
                "move_id": move.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "picking_id": self.picking.id,
        }
        line_values[MobileInventoryService(self.env)._done_quantity_field()] = 0
        self.env["stock.move.line"].create(line_values)

    def _create_picking(self, picking_type, product, quantity=1):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom_qty": quantity,
                "product_uom": product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
            }
        )
        values = {
            "move_id": move.id,
            "product_id": product.id,
            "product_uom_id": product.uom_id.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
            "picking_id": picking.id,
        }
        values[MobileInventoryService(self.env)._done_quantity_field()] = 0
        line = self.env["stock.move.line"].create(values)
        return picking, line

    def test_scan_idempotent(self):
        service = MobileInventoryService(self.env)
        payload = {
            "event_id": "event-1",
            "code": "ABC123",
            "qty": 1,
            "record_version": service._record_version(self.picking),
        }
        first = service.scan(self.picking.id, payload, device_id="device-1", event_id="event-1")
        second = service.scan(self.picking.id, payload, device_id="device-1", event_id="event-1")
        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        line = self.picking.move_line_ids[0]
        self.assertEqual(service._line_done_qty(line), 1)
        receipts = self.env["mobile.outbox.receipt"].search([
            ("event_id", "=", "event-1")
        ])
        self.assertEqual(len(receipts), 1)

    def test_scan_replay_ignores_stale_version_without_incrementing_again(self):
        service = MobileInventoryService(self.env)
        initial_version = service._record_version(self.picking)
        payload = {
            "event_id": "event-stale-replay",
            "code": "ABC123",
            "qty": 1,
            "record_version": initial_version,
        }
        service.scan(
            self.picking.id,
            payload,
            device_id="device-1",
            event_id=payload["event_id"],
        )
        self.assertNotEqual(initial_version, service._record_version(self.picking))
        replay = service.scan(
            self.picking.id,
            payload,
            device_id="device-1",
            event_id=payload["event_id"],
        )
        self.assertEqual(replay["status"], "success")
        self.assertEqual(service._line_done_qty(self.picking.move_line_ids[0]), 1)

    def test_update_line_sets_absolute_quantity_and_is_idempotent(self):
        service = MobileInventoryService(self.env)
        line = self.picking.move_line_ids[0]
        payload = {
            "event_id": "event-absolute-qty",
            "qty_done": 3,
            "record_version": service._record_version(self.picking),
        }
        first = service.update_line(
            self.picking.id,
            line.id,
            payload,
            device_id="device-1",
            event_id=payload["event_id"],
        )
        second = service.update_line(
            self.picking.id,
            line.id,
            payload,
            device_id="device-1",
            event_id=payload["event_id"],
        )
        self.assertEqual(first["line"]["qty_done"], 3)
        self.assertEqual(second["line"]["qty_done"], 3)
        self.assertEqual(service._line_done_qty(line), 3)

    def test_update_line_rejects_lot_for_untracked_product(self):
        service = MobileInventoryService(self.env)
        line = self.picking.move_line_ids[0]
        with self.assertRaisesRegex(UserError, "does not use lot"):
            service.update_line(
                self.picking.id,
                line.id,
                {
                    "event_id": "event-invalid-lot",
                    "qty_done": 1,
                    "lot_name": "LOT-001",
                },
                device_id="device-1",
                event_id="event-invalid-lot",
            )

    def test_scan_rejects_closed_transfer(self):
        service = MobileInventoryService(self.env)
        self.picking.action_cancel()
        with self.assertRaisesRegex(UserError, "cannot be scanned"):
            service.scan(
                self.picking.id,
                {"code": "ABC123", "qty": 1},
                device_id="device-1",
                event_id="event-closed-scan",
            )

    def test_scan_rejects_ambiguous_product_lines(self):
        service = MobileInventoryService(self.env)
        original = self.picking.move_line_ids[0]
        original.copy()
        with self.assertRaisesRegex(UserError, "Multiple move lines"):
            service.scan(
                self.picking.id,
                {"code": "ABC123", "qty": 1},
                device_id="device-1",
                event_id="event-ambiguous-scan",
            )

    def test_validate_partial_transfer_requires_explicit_backorder_decision(self):
        service = MobileInventoryService(self.env)
        self.picking.action_confirm()
        line = self.picking.move_line_ids[0]
        line.write({service._done_quantity_field(): 0.5})
        response = service.validate(
            self.picking.id,
            {
                "event_id": "event-backorder-ask",
                "record_version": service._record_version(self.picking),
                "backorder_policy": "ask",
            },
            device_id="device-1",
            event_id="event-backorder-ask",
        )
        self.assertEqual(response["status"], "needs_backorder")
        self.assertTrue(response["backorder_required"])
        self.assertNotEqual(self.picking.state, "done")
        self.assertFalse(
            self.env["mobile.outbox.receipt"].search(
                [("event_id", "=", "event-backorder-ask")]
            )
        )

    def test_validate_partial_transfer_creates_backorder(self):
        service = MobileInventoryService(self.env)
        self.picking.action_confirm()
        line = self.picking.move_line_ids[0]
        line.write({service._done_quantity_field(): 0.5})
        response = service.validate(
            self.picking.id,
            {
                "event_id": "event-backorder-create",
                "record_version": service._record_version(self.picking),
                "backorder_policy": "create",
            },
            device_id="device-1",
            event_id="event-backorder-create",
        )
        self.assertEqual(response["status"], "success")
        self.assertEqual(self.picking.state, "done")
        self.assertTrue(response["backorder_picking_id"])
        backorder = self.env["stock.picking"].browse(response["backorder_picking_id"])
        self.assertEqual(backorder.backorder_id, self.picking)
        self.assertNotIn(backorder.state, ("done", "cancel"))

    def test_validate_partial_transfer_cancels_remainder(self):
        service = MobileInventoryService(self.env)
        self.picking.action_confirm()
        line = self.picking.move_line_ids[0]
        line.write({service._done_quantity_field(): 0.5})
        response = service.validate(
            self.picking.id,
            {
                "event_id": "event-backorder-cancel",
                "record_version": service._record_version(self.picking),
                "backorder_policy": "cancel",
            },
            device_id="device-1",
            event_id="event-backorder-cancel",
        )
        self.assertEqual(response["status"], "success")
        self.assertEqual(self.picking.state, "done")
        self.assertFalse(response["backorder_picking_id"])
        active_backorders = self.env["stock.picking"].search(
            [("backorder_id", "=", self.picking.id), ("state", "!=", "cancel")]
        )
        self.assertFalse(active_backorders)

    def test_receipt_accepts_and_creates_new_tracked_lot(self):
        service = MobileInventoryService(self.env)
        product = self.env["product.product"].create(
            {"name": "Tracked Receipt Product", "tracking": "lot"}
        )
        picking_type = self.env.ref("stock.picking_type_in")
        picking_type.write({"use_create_lots": True})
        picking, line = self._create_picking(picking_type, product, quantity=2)
        update = service.update_line(
            picking.id,
            line.id,
            {
                "event_id": "event-new-receipt-lot",
                "qty_done": 2,
                "record_version": service._record_version(picking),
                "lot_name": "MOBILE-LOT-001",
            },
            device_id="device-1",
            event_id="event-new-receipt-lot",
        )
        self.assertEqual(update["line"]["lot_name"], "MOBILE-LOT-001")
        response = service.validate(
            picking.id,
            {
                "event_id": "event-new-receipt-lot-validate",
                "record_version": service._record_version(picking),
                "backorder_policy": "ask",
            },
            device_id="device-1",
            event_id="event-new-receipt-lot-validate",
        )
        self.assertEqual(response["status"], "success")
        self.assertEqual(picking.state, "done")
        lot = self.env["stock.lot"].search(
            [("name", "=", "MOBILE-LOT-001"), ("product_id", "=", product.id)]
        )
        self.assertTrue(lot)

    def test_detail_exposes_demand_without_move_lines_and_creates_serial_lines(self):
        service = MobileInventoryService(self.env)
        product = self.env["product.product"].create(
            {"name": "Serial Receipt Product", "tracking": "serial"}
        )
        picking_type = self.env.ref("stock.picking_type_in")
        picking_type.write({"use_create_lots": True})
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom_qty": 2,
                "product_uom": product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
            }
        )
        detail = service.get_picking_detail(picking.id)
        self.assertFalse(detail["lines"])
        self.assertEqual(detail["moves"][0]["id"], move.id)
        self.assertEqual(detail["moves"][0]["qty_demanded"], 2)

        first = service.create_line(
            picking.id,
            {
                "event_id": "event-serial-line-1",
                "move_id": move.id,
                "qty_done": 1,
                "record_version": detail["record_version"],
                "lot_name": "SERIAL-001",
            },
            device_id="device-1",
            event_id="event-serial-line-1",
        )
        second = service.create_line(
            picking.id,
            {
                "event_id": "event-serial-line-2",
                "move_id": move.id,
                "qty_done": 1,
                "record_version": first["record_version"],
                "lot_name": "SERIAL-002",
            },
            device_id="device-1",
            event_id="event-serial-line-2",
        )
        self.assertEqual(first["line"]["move_id"], move.id)
        self.assertEqual(second["line"]["move_id"], move.id)
        self.assertEqual(len(picking.move_line_ids), 2)
