from datetime import datetime, time, timedelta, timezone

from odoo import fields
from odoo.tests.common import tagged

from odoo.addons.fastapi.tests.common import FastAPITransactionCase
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..routers import router as mobile_router


@tagged("post_install", "-at_install")
class TestMobileApiManufacturingWorkflows(FastAPITransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref("mrp.group_mrp_user", raise_if_not_found=False)
        groups = [cls.env.ref("base.group_user").id]
        if group:
            groups.append(group.id)
        quality_group = cls.env.ref(
            "hg_quality.group_quality_operator", raise_if_not_found=False
        )
        if quality_group:
            groups.append(quality_group.id)
        cls.user = cls.env["res.users"].create(
            {
                "name": "Manufacturing Mobile User",
                "login": "manufacturing.mobile.user",
                "email": "manufacturing.mobile.user@example.com",
                "groups_id": [(6, 0, groups)],
            }
        )
        cls.assigned_user = cls.env["res.users"].create(
            {
                "name": "Assigned Work Order Employee",
                "login": "assigned.work.order.employee",
                "email": "assigned.work.order.employee@example.com",
                "groups_id": [(6, 0, groups)],
            }
        )
        mrp_only_groups = [cls.env.ref("base.group_user").id]
        if group:
            mrp_only_groups.append(group.id)
        cls.mrp_only_user = cls.env["res.users"].create(
            {
                "name": "Manufacturing User Without Quality Access",
                "login": "manufacturing.without.quality",
                "email": "manufacturing.without.quality@example.com",
                "groups_id": [(6, 0, mrp_only_groups)],
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Mobile Manufacturing Product",
                "type": "consu",
                "is_storable": True,
            }
        )
        now = fields.Datetime.now()
        cls.attention_order = cls.env["mrp.production"].create(
            {
                "product_id": cls.product.id,
                "product_qty": 6,
                "product_uom_id": cls.product.uom_id.id,
                "date_start": now - timedelta(hours=1),
                "date_deadline": now - timedelta(minutes=10),
                "user_id": cls.user.id,
            }
        )
        today_deadline = datetime.combine(now.date(), time(23, 59, 59))
        cls.today_order = cls.env["mrp.production"].create(
            {
                "product_id": cls.product.id,
                "product_qty": 4,
                "product_uom_id": cls.product.uom_id.id,
                "date_start": today_deadline,
                "date_deadline": today_deadline,
                "user_id": cls.user.id,
            }
        )
        cls.future_order = cls.env["mrp.production"].create(
            {
                "product_id": cls.product.id,
                "product_qty": 2,
                "product_uom_id": cls.product.uom_id.id,
                "date_start": now + timedelta(days=3),
                "date_deadline": now + timedelta(days=4),
            }
        )

    def _client(self, user=None):
        user = user or self.user
        overrides = {auth_jwt_authenticated_odoo_env: lambda: self.env(user=user.id)}
        return self._create_test_client(
            router=mobile_router,
            dependency_overrides=overrides,
            raise_server_exceptions=False,
        )

    def test_quality_permissions_are_not_elevated_by_mobile_api(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.mrp_only_user.id,
            }
        )
        with self._client(self.mrp_only_user) as client:
            detail = client.get(f"/v1/manufacturing/orders/{order.id}")
            create = client.post(
                "/v1/manufacturing/orders",
                json={"product_id": self.product.id, "quantity": 1},
            )
        self.assertEqual(detail.status_code, 403, detail.text)
        self.assertEqual(create.status_code, 403, create.text)

    def _quality_check(self, order, control_type="passfail", failure_action="block"):
        point = self.env["hg.quality.point"].create(
            {
                "name": f"Mobile {control_type} check",
                "control_type": control_type,
                "failure_action": failure_action,
            }
        )
        return self.env["hg.quality.check"].create(
            {"production_id": order.id, "point_id": point.id}
        )

    def test_due_or_late_orders_returns_open_attention_work(self):
        with self._client() as client:
            response = client.get("/v1/manufacturing/orders?attention=due_or_late&limit=50")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        ids = [item["id"] for item in payload]
        self.assertIn(self.attention_order.id, ids)
        self.assertIn(self.today_order.id, ids)
        self.assertNotIn(self.future_order.id, ids)
        item = next(item for item in payload if item["id"] == self.attention_order.id)
        self.assertEqual(item["product_name"], self.product.display_name)
        self.assertIn(item["attention_reason"], ["overdue", "planned_overdue"])
        today_item = next(item for item in payload if item["id"] == self.today_order.id)
        self.assertIn(today_item["attention_reason"], ["due_today", "planned_today"])

    def test_assignees_returns_manufacturing_users(self):
        with self._client() as client:
            response = client.get("/v1/manufacturing/assignees?limit=50")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        ids = [item["id"] for item in payload]
        self.assertIn(self.user.id, ids)
        self.assertIn(self.assigned_user.id, ids)
        item = next(item for item in payload if item["id"] == self.assigned_user.id)
        self.assertEqual(item["name"], self.assigned_user.display_name)

    def test_order_detail_returns_components_list_shape(self):
        with self._client() as client:
            response = client.get(f"/v1/manufacturing/orders/{self.attention_order.id}")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], self.attention_order.id)
        self.assertEqual(payload["name"], self.attention_order.name)
        self.assertIn("components", payload)

    def test_create_order_makes_mobile_work_order(self):
        deadline = (fields.Datetime.now() + timedelta(days=1)).replace(tzinfo=timezone.utc)
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={
                    "product_id": self.product.id,
                    "quantity": 3,
                    "assigned_user_id": self.assigned_user.id,
                    "deadline": deadline.isoformat(),
                    "notes": "Mobile work order note",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        order = payload["order"]
        self.assertEqual(order["product_id"], self.product.id)
        self.assertEqual(order["quantity"], 3)
        self.assertEqual(order["assigned_user_name"], self.assigned_user.display_name)

        production = self.env["mrp.production"].browse(order["id"]).exists()
        self.assertTrue(production)
        self.assertEqual(production.product_id, self.product)
        self.assertEqual(production.product_qty, 3)
        self.assertEqual(production.user_id, self.assigned_user)
        self.assertEqual(production.state, "draft")
        self.assertIsNone(production.date_deadline.tzinfo)
        self.assertEqual(production.origin, "Mobile work order note")

    def test_create_order_returns_404_for_missing_assignee(self):
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={
                    "product_id": self.product.id,
                    "quantity": 1,
                    "assigned_user_id": 99999999,
                },
            )
        self.assertEqual(response.status_code, 404, response.text)

    def test_create_order_preserves_fractional_quantity(self):
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={"product_id": self.product.id, "quantity": 0.5},
            )
        self.assertEqual(response.status_code, 200, response.text)
        order = self.env["mrp.production"].browse(response.json()["order"]["id"])
        self.assertEqual(order.product_qty, 0.5)

    def test_complete_order_marks_mobile_work_order_done(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()

        with self._client() as client:
            response = client.post(
                f"/v1/manufacturing/orders/{order.id}/complete",
                json={
                    "reviewed": True,
                    "quantity": 1,
                    "disposition": "close",
                    "components": [],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], order.id)
        self.assertEqual(payload["state"], "done")
        self.assertEqual(order.exists().state, "done")

    def test_completion_requires_explicit_review_payload(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()
        with self._client() as client:
            response = client.post(
                f"/v1/manufacturing/orders/{order.id}/complete",
                json={
                    "reviewed": False,
                    "quantity": 1,
                    "disposition": "close",
                    "components": [],
                },
            )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotEqual(order.exists().state, "done")

    def test_completion_review_returns_remaining_quantity(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()
        with self._client() as client:
            response = client.get(
                f"/v1/manufacturing/orders/{order.id}/completion-review"
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["order_id"], order.id)
        self.assertEqual(payload["suggested_quantity"], 2)
        self.assertEqual(payload["quantity_remaining"], 2)

    def test_partial_completion_creates_backorder(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 2,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()
        existing_ids = set(self.env["mrp.production"].search([]).ids)
        with self._client() as client:
            response = client.post(
                f"/v1/manufacturing/orders/{order.id}/complete",
                json={
                    "reviewed": True,
                    "quantity": 1,
                    "disposition": "backorder",
                    "components": [],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(order.state, "done")
        backorders = self.env["mrp.production"].search(
            [("id", "not in", list(existing_ids)), ("product_id", "=", self.product.id)]
        )
        self.assertEqual(len(backorders), 1)
        self.assertEqual(backorders.product_qty, 1)
        self.assertNotEqual(backorders.state, "done")

    def test_pending_blocking_quality_check_prevents_completion(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()
        check = self._quality_check(order)
        with self._client() as client:
            review = client.get(f"/v1/manufacturing/orders/{order.id}/completion-review")
            response = client.post(
                f"/v1/manufacturing/orders/{order.id}/complete",
                json={
                    "reviewed": True,
                    "quantity": 1,
                    "disposition": "close",
                    "components": [],
                },
            )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertFalse(review.json()["can_complete"])
        self.assertIn(check.id, review.json()["pending_quality_check_ids"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotEqual(order.state, "done")

    def test_photo_quality_endpoint_stores_evidence_and_passes(self):
        order = self.env["mrp.production"].create(
            {
                "product_id": self.product.id,
                "product_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "user_id": self.user.id,
            }
        )
        check = self._quality_check(order, control_type="picture")
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with self._client() as client:
            response = client.post(
                f"/v1/manufacturing/quality-checks/{check.id}/photo",
                json={
                    "image_base64": png,
                    "filename": "quality.png",
                    "notes": "Photo reviewed",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(check.state, "pass")
        self.assertTrue(check.picture)
        self.assertEqual(check.picture_filename, "quality.png")
        item = next(item for item in response.json()["quality_checks"] if item["id"] == check.id)
        self.assertTrue(item["has_photo"])

    def test_product_and_lot_lookup_are_product_scoped(self):
        tracked = self.env["product.product"].create(
            {
                "name": "Tracked Milling Wheat",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        lot = self.env["stock.lot"].create(
            {"name": "WHEAT-LOT-1", "product_id": tracked.id, "company_id": self.env.company.id}
        )
        with self._client() as client:
            products = client.get("/v1/manufacturing/products?search=Tracked%20Milling")
            lots = client.get(
                f"/v1/manufacturing/products/{tracked.id}/lots?search=WHEAT"
            )
        self.assertEqual(products.status_code, 200, products.text)
        self.assertIn(tracked.id, [item["id"] for item in products.json()])
        self.assertEqual(lots.status_code, 200, lots.text)
        self.assertEqual([item["id"] for item in lots.json()], [lot.id])

    def test_tracked_completion_records_finished_and_component_lots(self):
        finished = self.env["product.product"].create(
            {
                "name": "Lot Tracked Flour",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        component = self.env["product.product"].create(
            {
                "name": "Lot Tracked Wheat",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        component_lot = self.env["stock.lot"].create(
            {
                "name": "WHEAT-2026-09",
                "product_id": component.id,
                "company_id": self.env.company.id,
            }
        )
        stock_location = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"]._update_available_quantity(
            component, stock_location, 10, lot_id=component_lot
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished.product_tmpl_id.id,
                "product_qty": 1,
                "product_uom_id": finished.uom_id.id,
                "bom_line_ids": [
                    (0, 0, {"product_id": component.id, "product_qty": 2})
                ],
            }
        )
        order = self.env["mrp.production"].create(
            {
                "product_id": finished.id,
                "product_qty": 2,
                "product_uom_id": finished.uom_id.id,
                "bom_id": bom.id,
                "user_id": self.user.id,
            }
        )
        order.action_confirm()
        order.action_assign()
        move = order.move_raw_ids
        with self._client() as client:
            response = client.post(
                f"/v1/manufacturing/orders/{order.id}/complete",
                json={
                    "reviewed": True,
                    "quantity": 2,
                    "disposition": "close",
                    "finished_lot_name": "FLOUR-2026-09",
                    "components": [
                        {
                            "move_id": move.id,
                            "quantity": 4,
                            "lot_id": component_lot.id,
                        }
                    ],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(order.state, "done")
        self.assertEqual(order.lot_producing_id.name, "FLOUR-2026-09")
        self.assertEqual(move.state, "done")
        self.assertEqual(move.move_line_ids.lot_id, component_lot)
        self.assertEqual(move.quantity, 4)

    def test_create_order_returns_404_for_missing_product(self):
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={"product_id": 99999999, "quantity": 1},
            )
        self.assertEqual(response.status_code, 404, response.text)

    def test_work_list_only_returns_orders_assigned_to_signed_in_user(self):
        self.future_order.write({"user_id": self.assigned_user.id})
        with self._client() as client:
            response = client.get("/v1/manufacturing/orders?attention=all&limit=200")
        self.assertEqual(response.status_code, 200, response.text)
        ids = [item["id"] for item in response.json()]
        self.assertIn(self.attention_order.id, ids)
        self.assertNotIn(self.future_order.id, ids)

    def test_settings_administrator_sees_other_assignees(self):
        from ..services.manufacturing_service import MobileManufacturingService
        self.user.write({"groups_id": [(4, self.env.ref("base.group_system").id)]})
        self.future_order.write({"user_id": self.assigned_user.id})
        items = MobileManufacturingService(self.env(user=self.user.id)).list_orders(attention="all", limit=200)
        self.assertIn(self.future_order.id, [item["id"] for item in items])
