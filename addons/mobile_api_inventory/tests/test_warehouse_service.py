from odoo.tests.common import tagged

from odoo.addons.base.tests.common import BaseCommon

from ..services.inventory_service import MobileInventoryService
from ..services.warehouse_service import MobileWarehouseService


@tagged("post_install", "-at_install")
class TestWarehouseService(BaseCommon):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create(
            {
                "name": "Warehouse Workflow Product",
                "barcode": "WAREHOUSE-001",
                "is_storable": True,
            }
        )
        self.location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.location, 10
        )
        self.quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.location.id),
                ("lot_id", "=", False),
                ("package_id", "=", False),
                ("owner_id", "=", False),
            ],
            limit=1,
        )
        self.service = MobileWarehouseService(self.env)

    def test_stock_lookup_and_count_adjustment_review_apply(self):
        lookup = self.service.stock(query="WAREHOUSE-001")
        item = next(row for row in lookup["items"] if row["id"] == self.quant.id)
        self.assertEqual(item["quantity"], 10)
        self.assertTrue(lookup["can_adjust"])

        review = self.service.review_adjustment(self.quant.id, 8)
        self.assertEqual(review["current_quantity"], 10)
        self.assertEqual(review["difference"], -2)
        applied = self.service.apply_adjustment(
            {
                "event_id": "warehouse-count-1",
                "device_id": "warehouse-device",
                "quant_id": self.quant.id,
                "counted_quantity": 8,
                "record_version": review["record_version"],
                "reviewed": True,
            }
        )
        self.assertEqual(applied["status"], "success")
        self.assertEqual(self.quant.quantity, 8)
        replay = self.service.apply_adjustment(
            {
                "event_id": "warehouse-count-1",
                "device_id": "warehouse-device",
                "quant_id": self.quant.id,
                "counted_quantity": 8,
                "record_version": review["record_version"],
                "reviewed": True,
            }
        )
        self.assertEqual(replay["status"], "success")
        self.assertEqual(self.quant.quantity, 8)

    def test_scrap_review_apply_uses_odoo_workflow(self):
        review = self.service.review_scrap(self.quant.id, 2)
        self.assertTrue(review["reviewed"])
        self.assertEqual(review["available_quantity"], 10)
        applied = self.service.apply_scrap(
            {
                "event_id": "warehouse-scrap-1",
                "device_id": "warehouse-device",
                "quant_id": self.quant.id,
                "quantity": 2,
                "record_version": review["record_version"],
                "reviewed": True,
            }
        )
        self.assertEqual(applied["status"], "success")
        self.assertEqual(applied["state"], "done")
        self.assertEqual(self.quant.quantity, 8)

    def test_return_review_apply_uses_return_wizard(self):
        picking_type = self.env.ref("stock.picking_type_in")
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": self.product.display_name,
                "product_id": self.product.id,
                "product_uom_qty": 3,
                "product_uom": self.product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "picking_id": picking.id,
            }
        )
        line_values = {
            "move_id": move.id,
            "picking_id": picking.id,
            "product_id": self.product.id,
            "product_uom_id": self.product.uom_id.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
        }
        inventory = MobileInventoryService(self.env)
        line_values[inventory._done_quantity_field()] = 3
        self.env["stock.move.line"].create(line_values)
        result = picking.button_validate()
        self.assertTrue(result)
        self.assertEqual(picking.state, "done")

        review = self.service.review_return(picking.id)
        reviewed_line = next(row for row in review["lines"] if row["move_id"] == move.id)
        self.assertEqual(reviewed_line["quantity"], 3)
        applied = self.service.apply_return(
            picking.id,
            {
                "event_id": "warehouse-return-1",
                "device_id": "warehouse-device",
                "record_version": review["record_version"],
                "reviewed": True,
                "lines": [{"move_id": move.id, "quantity": 1}],
            },
        )
        self.assertEqual(applied["status"], "success")
        returned = self.env["stock.picking"].browse(applied["new_picking_id"])
        self.assertEqual(returned.return_id, picking)
        self.assertEqual(returned.move_ids.product_uom_qty, 1)
        second_review = self.service.review_return(picking.id)
        remaining = next(
            row for row in second_review["lines"] if row["move_id"] == move.id
        )
        self.assertEqual(remaining["quantity"], 2)
