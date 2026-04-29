from odoo.tests.common import tagged

from odoo.addons.fastapi.tests.common import FastAPITransactionCase
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..routers import router as mobile_router


@tagged("post_install", "-at_install")
class TestMobileApiSmartLabelWorkflows(FastAPITransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_xmlids = [
            "base.group_user",
            "mrp.group_mrp_user",
            "stock.group_stock_manager",
            "product.group_product_manager",
        ]
        groups = []
        for xmlid in group_xmlids:
            group = cls.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups.append(group.id)
        cls.user = cls.env["res.users"].create(
            {
                "name": "Smart Label Mobile User",
                "login": "smart.label.mobile.user",
                "email": "smart.label.mobile.user@example.com",
                "groups_id": [(6, 0, groups)],
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Mobile Label Product",
                "lst_price": 8.95,
            }
        )
        cls.no_barcode_product = cls.env["product.product"].create(
            {
                "name": "Mobile Label Product Without Barcode",
                "lst_price": 9.95,
            }
        )
        cls.device = cls.env["smart.label.device"].create({"name": "Mobile Printer"})

    def _client(self):
        overrides = {auth_jwt_authenticated_odoo_env: lambda: self.env(user=self.user.id)}
        return self._create_test_client(
            router=mobile_router,
            dependency_overrides=overrides,
            raise_server_exceptions=False,
        )

    def test_queue_job_uses_wizard_and_barcode_business_logic(self):
        with self._client() as client:
            response = client.post(
                "/v1/smart-label/jobs",
                json={
                    "product_id": self.product.id,
                    "device_id": self.device.id,
                    "barcode": "012345678905",
                    "quantity": 2,
                    "label_type": "back",
                    "update_inventory": True,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        job = self.env["smart.label.job"].browse(payload["job"]["id"]).exists()
        self.assertTrue(job)
        self.assertEqual(job.product_id, self.product)
        self.assertEqual(job.device_id, self.device)
        self.assertEqual(job.quantity, 2)
        self.assertEqual(job.label_type, "back")
        self.assertEqual(self.product.barcode, "012345678905")
        self.assertTrue(job.profile_id)

    def test_queue_job_maps_wizard_user_error_to_400(self):
        with self._client() as client:
            response = client.post(
                "/v1/smart-label/jobs",
                json={
                    "product_id": self.no_barcode_product.id,
                    "quantity": 1,
                    "label_type": "back",
                },
            )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Enter a barcode", response.json()["detail"])

    def test_product_search_uses_sql_safe_fields(self):
        product = self.env["product.product"].create(
            {
                "name": "Sifted Mobile Flour",
                "default_code": "SIFTED-MOBILE",
                "barcode": "998877665544",
                "lst_price": 7.95,
            }
        )
        with self._client() as client:
            response = client.get("/v1/smart-label/products?query=sifted&limit=20")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        product_ids = [item["id"] for item in payload]
        self.assertIn(product.id, product_ids)

    def test_cancel_and_reset_job_call_object_methods(self):
        action_product = self.env["product.product"].create(
            {
                "name": "Mobile Label Action Product",
                "lst_price": 10.95,
            }
        )
        job = self.env["smart.label.job"].create(
            self.env["smart.label.profile"]
            .create({"product_id": action_product.id})
            .prepare_job_values(quantity=1, label_type="front", device=self.device)
        )
        with self._client() as client:
            cancel_response = client.post(
                f"/v1/smart-label/jobs/{job.id}/cancel",
                json={"client_action_id": "cancel-1"},
            )
            reset_response = client.post(
                f"/v1/smart-label/jobs/{job.id}/reset",
                json={"client_action_id": "reset-1"},
            )
        self.assertEqual(cancel_response.status_code, 200, cancel_response.text)
        self.assertEqual(cancel_response.json()["job"]["state"], "cancelled")
        self.assertEqual(reset_response.status_code, 200, reset_response.text)
        self.assertEqual(reset_response.json()["job"]["state"], "pending")
        self.assertEqual(self.env["smart.label.job"].browse(job.id).state, "pending")

    def test_cancel_missing_job_returns_404(self):
        with self._client() as client:
            response = client.post(
                "/v1/smart-label/jobs/999999/cancel",
                json={"client_action_id": "missing-1"},
            )
        self.assertEqual(response.status_code, 404, response.text)

    def test_rotate_device_token_calls_object_method(self):
        old_token = self.device.agent_token
        with self._client() as client:
            response = client.post(
                f"/v1/smart-label/devices/{self.device.id}/rotate-token",
                json={"client_action_id": "rotate-1"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()["agent_token"], old_token)
        self.device.invalidate_recordset(["agent_token"])
        self.assertEqual(response.json()["agent_token"], self.device.agent_token)
