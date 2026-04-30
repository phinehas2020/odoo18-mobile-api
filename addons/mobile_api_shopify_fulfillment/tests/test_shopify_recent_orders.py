from datetime import timedelta

from odoo import fields
from odoo.tests.common import tagged

from odoo.addons.fastapi.tests.common import FastAPITransactionCase
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..routers import router as mobile_router


@tagged("post_install", "-at_install")
class TestMobileApiShopifyRecentOrders(FastAPITransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "Shopify Fulfillment Mobile User",
                "login": "shopify.fulfillment.mobile.user",
                "email": "shopify.fulfillment.mobile.user@example.com",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        now = fields.Datetime.now()
        cls.recent_order = cls.env["shopify.order"].create(
            {
                "shopify_id": "1000001",
                "order_name": "#1001",
                "customer_name": "Recent Customer",
                "created_at": now - timedelta(hours=2),
                "source": "shopify",
                "state": "pending",
                "requested_shipping_method": "Ground",
            }
        )
        cls.old_order = cls.env["shopify.order"].create(
            {
                "shopify_id": "1000002",
                "order_name": "#1002",
                "customer_name": "Old Customer",
                "created_at": now - timedelta(days=3),
                "source": "shopify",
                "state": "pending",
            }
        )
        cls.pos_order = cls.env["shopify.order"].create(
            {
                "shopify_id": "1000003",
                "order_name": "#1003",
                "customer_name": "POS Customer",
                "created_at": now - timedelta(hours=1),
                "source": "pos",
                "state": "pending",
            }
        )

    def _client(self):
        overrides = {auth_jwt_authenticated_odoo_env: lambda: self.env(user=self.user.id)}
        return self._create_test_client(
            router=mobile_router,
            dependency_overrides=overrides,
            raise_server_exceptions=False,
        )

    def test_recent_orders_filters_to_shopify_orders_inside_window(self):
        with self._client() as client:
            response = client.get("/v1/shopify/orders/recent?hours=24&limit=50")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        ids = [item["id"] for item in payload]
        self.assertIn(self.recent_order.id, ids)
        self.assertNotIn(self.old_order.id, ids)
        self.assertNotIn(self.pos_order.id, ids)
        item = next(item for item in payload if item["id"] == self.recent_order.id)
        self.assertEqual(item["order_name"], "#1001")
        self.assertEqual(item["requested_shipping_method"], "Ground")

