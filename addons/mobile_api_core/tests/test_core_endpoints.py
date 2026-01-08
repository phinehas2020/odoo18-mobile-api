from odoo.tests.common import tagged

from odoo.addons.fastapi.tests.common import FastAPITransactionCase
from odoo.addons.fastapi_auth_jwt.dependencies import auth_jwt_authenticated_odoo_env

from ..routers import router as mobile_router


@tagged("post_install", "-at_install")
class TestMobileApiCore(FastAPITransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "Mobile User",
                "login": "mobile.user",
                "email": "mobile.user@example.com",
                "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_health(self):
        with self._create_test_client(router=mobile_router) as client:
            response = client.get("/v1/health")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload.get("status"), "ok")

    def test_me_requires_auth(self):
        with self._create_test_client(router=mobile_router, raise_server_exceptions=False) as client:
            response = client.get("/v1/me")
            self.assertEqual(response.status_code, 401)

    def test_me_authenticated(self):
        overrides = {auth_jwt_authenticated_odoo_env: lambda: self.env(user=self.user.id)}
        with self._create_test_client(router=mobile_router, dependency_overrides=overrides) as client:
            response = client.get("/v1/me")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload.get("login"), "mobile.user")
