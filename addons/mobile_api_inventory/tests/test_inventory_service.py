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
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "qty_done": 0,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "picking_id": self.picking.id,
            }
        )

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
        self.assertEqual(line.qty_done, 1)
        receipts = self.env["mobile.outbox.receipt"].search([
            ("event_id", "=", "event-1")
        ])
        self.assertEqual(len(receipts), 1)
