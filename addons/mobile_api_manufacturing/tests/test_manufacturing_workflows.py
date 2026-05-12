from datetime import datetime, time, timedelta

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
        cls.user = cls.env["res.users"].create(
            {
                "name": "Manufacturing Mobile User",
                "login": "manufacturing.mobile.user",
                "email": "manufacturing.mobile.user@example.com",
                "groups_id": [(6, 0, groups)],
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Mobile Manufacturing Product",
                "type": "product",
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

    def _client(self):
        overrides = {auth_jwt_authenticated_odoo_env: lambda: self.env(user=self.user.id)}
        return self._create_test_client(
            router=mobile_router,
            dependency_overrides=overrides,
            raise_server_exceptions=False,
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

    def test_order_detail_returns_components_list_shape(self):
        with self._client() as client:
            response = client.get(f"/v1/manufacturing/orders/{self.attention_order.id}")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], self.attention_order.id)
        self.assertEqual(payload["name"], self.attention_order.name)
        self.assertIn("components", payload)

    def test_create_order_makes_mobile_work_order(self):
        deadline = fields.Datetime.now() + timedelta(days=1)
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={
                    "product_id": self.product.id,
                    "quantity": 3,
                    "deadline": deadline.isoformat(),
                    "notes": "Mobile work order note",
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        order = payload["order"]
        self.assertEqual(order["product_id"], self.product.id)
        self.assertEqual(order["quantity"], 3)
        self.assertEqual(order["assigned_user_name"], self.user.display_name)

        production = self.env["mrp.production"].browse(order["id"]).exists()
        self.assertTrue(production)
        self.assertEqual(production.product_id, self.product)
        self.assertEqual(production.product_qty, 3)
        self.assertEqual(production.user_id, self.user)
        self.assertEqual(production.origin, "Mobile work order note")

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
            response = client.post(f"/v1/manufacturing/orders/{order.id}/complete")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["id"], order.id)
        self.assertEqual(payload["state"], "done")
        self.assertEqual(order.exists().state, "done")

    def test_create_order_returns_404_for_missing_product(self):
        with self._client() as client:
            response = client.post(
                "/v1/manufacturing/orders",
                json={"product_id": 99999999, "quantity": 1},
            )
        self.assertEqual(response.status_code, 404, response.text)
