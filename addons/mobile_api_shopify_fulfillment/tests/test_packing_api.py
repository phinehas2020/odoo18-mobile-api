"""Security and retry contracts using disposable records, with no provider calls."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from odoo.tests.common import tagged
from odoo.addons.fastapi.tests.common import FastAPITransactionCase
from odoo.addons.fastapi_auth_jwt.dependencies import (
    auth_jwt_authenticated_odoo_env,
    auth_jwt_authenticated_payload,
)
from odoo.addons.shopify_fulfillment.services.packing_utils import PACKING_MOBILE_REQUEST, PackingError

from ..routers import router as mobile_router
from ..schemas.packing import PackingDetail, PackingQuantityRequest, PackingResolveRequest
from ..services.packing_service import MobilePackingService


def detail_fixture(shipment_id=101):
    return {
        "shipment_id": shipment_id,
        "order_id": 201,
        "order_name": "#PackingFixture",
        "customer_name": "Fixture Customer",
        "tracking_number": "1Z999AA10123456784",
        "carrier": "UPS",
        "box_number": 1,
        "box_count": 1,
        "packing_state": "unstarted",
        "operational_state": "pending",
        "sync_state": "not_ready",
        "version": 3,
        "workflow_version": "packing_v1",
        "items": [{
            "line_id": 301,
            "title": "Cornmeal",
            "required_quantity": 2,
            "confirmed_quantity": 0,
            "remaining_quantity": 2,
        }],
        "siblings": [],
        "allowed_actions": {"claim": True, "edit": False, "complete": False},
    }


@tagged("post_install", "-at_install")
class TestPackingApi(FastAPITransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = [cls.env.ref("base.group_user").id, cls.env.ref("shopify_fulfillment.group_packing_employee").id]
        cls.user = cls.env["res.users"].create({
            "name": "Packing API Fixture",
            "login": "packing.api.fixture",
            "groups_id": [(6, 0, groups)],
            "company_id": cls.env.company.id,
            "company_ids": [(6, 0, [cls.env.company.id])],
        })
        cls.device_id = str(uuid4())
        cls.device = cls.env["mobile.device"].create({"user_id": cls.user.id, "device_id": cls.device_id})

    def _client(self, payload=None):
        claims = payload or {
            "uid": self.user.id,
            "device_id": self.device_id,
            "company_id": self.user.company_id.id,
            "allowed_company_ids": self.user.company_ids.ids,
        }
        return self._create_test_client(
            router=mobile_router,
            dependency_overrides={
                auth_jwt_authenticated_odoo_env: lambda: self.env(user=self.user.id),
                auth_jwt_authenticated_payload: lambda: claims,
            },
            raise_server_exceptions=False,
        )

    def _headers(self):
        # JWT verification itself is supplied by the dependency override, keeping
        # these fixtures independent of signing secrets or live credentials.
        return {"Authorization": "Bearer fixture", "X-Device-ID": self.device_id}

    def _resolve(self, claims=None, device_id=None, headers=None):
        with self._client(claims) as client:
            return client.post(
                "/v1/shopify/packing/resolve",
                headers=self._headers() if headers is None else headers,
                json={"barcode": "1Z999AA10123456784", "symbology": "code128", "device_id": device_id or self.device_id},
            )

    def test_resolver_is_read_only_and_not_cached(self):
        with patch.object(MobilePackingService, "resolve", autospec=True, return_value=detail_fixture()) as lookup:
            response = self._resolve()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["operational_state"], "pending")
        lookup.assert_called_once()
        scoped_service = lookup.call_args.args[0]
        self.assertFalse(scoped_service.env.su)
        self.assertEqual(scoped_service.env.context["allowed_company_ids"], [self.user.company_id.id])
        self.assertIs(scoped_service.env.context["_packing_mobile_request"], PACKING_MOBILE_REQUEST)

    def test_body_device_must_match_the_signed_device(self):
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve(device_id="another-device")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "device_mismatch")
        lookup.assert_not_called()

    def test_revoked_device_cannot_lookup(self):
        self.device.write({"revoked_at": "2026-10-05 00:00:00"})
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve()
        self.assertEqual(response.status_code, 401, response.text)
        lookup.assert_not_called()

    def test_device_cannot_be_used_by_another_employee(self):
        self.device.write({"user_id": self.env.ref("base.user_admin").id})
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve()
        self.assertEqual(response.status_code, 401, response.text)
        lookup.assert_not_called()

    def test_company_must_be_explicit_and_currently_allowed(self):
        claims = {"uid": self.user.id, "device_id": self.device_id, "company_id": 987654, "allowed_company_ids": [987654]}
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve(claims=claims)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "company_scope_required")
        lookup.assert_not_called()

    def test_uid_must_match_authenticated_environment(self):
        claims = {"uid": self.env.ref("base.user_admin").id, "device_id": self.device_id, "company_id": self.user.company_id.id, "allowed_company_ids": self.user.company_ids.ids}
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve(claims=claims)
        self.assertEqual(response.status_code, 401, response.text)
        lookup.assert_not_called()

    def test_packing_permission_is_required(self):
        self.user.write({"groups_id": [(6, 0, [self.env.ref("base.group_user").id])]})
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve()
        self.assertEqual(response.status_code, 403, response.text)
        lookup.assert_not_called()

    def test_cookie_authentication_is_not_accepted(self):
        with patch.object(MobilePackingService, "resolve") as lookup:
            response = self._resolve(headers={"X-Device-ID": self.device_id})
        self.assertEqual(response.status_code, 401, response.text)
        lookup.assert_not_called()

    def test_disabled_native_flow_blocks_writes_even_when_domain_enabled(self):
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("fulfillment.packing_enabled", "true")
        config.set_param("fulfillment.packing_native_enabled", "false")
        with patch.object(MobilePackingService, "shipment") as shipment:
            with self._client() as client:
                response = client.post(
                    "/v1/shopify/packing/101/complete",
                    headers=self._headers(),
                    json={"barcode": "1Z999AA10123456784", "version": 3, "event_id": str(uuid4()), "device_id": self.device_id},
                )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "packing_disabled")
        shipment.assert_not_called()

    def test_capabilities_requires_same_device_header(self):
        with self._client() as client:
            response = client.get("/v1/shopify/packing/capabilities", headers={"Authorization": "Bearer fixture", "X-Device-ID": "another-device"})
        self.assertEqual(response.status_code, 403, response.text)

    def test_native_preview_does_not_enable_business_mutations(self):
        config = self.env["ir.config_parameter"].sudo()
        config.set_param("fulfillment.packing_enabled", "false")
        config.set_param("fulfillment.packing_native_enabled", "true")
        with self._client() as client:
            capabilities = client.get("/v1/shopify/packing/capabilities", headers=self._headers())
        self.assertEqual(capabilities.status_code, 200, capabilities.text)
        self.assertTrue(capabilities.json()["enabled"])
        self.assertFalse(capabilities.json()["business_enabled"])
        with patch.object(MobilePackingService, "resolve", return_value=detail_fixture()) as lookup:
            response = self._resolve()
        self.assertEqual(response.status_code, 200, response.text)
        lookup.assert_called_once()
        with patch.object(MobilePackingService, "shipment") as shipment:
            with self._client() as client:
                response = client.patch(
                    "/v1/shopify/packing/101/items/301", headers=self._headers(),
                    json={"quantity": 2, "version": 3, "event_id": str(uuid4()), "device_id": self.device_id},
                )
        self.assertEqual(response.status_code, 409, response.text)
        shipment.assert_not_called()

    def test_rejected_domain_action_rolls_back_before_http_error_conversion(self):
        service = MobilePackingService(self.env, self.device_id)
        previous_name = self.device.device_name

        def rejected_operation():
            self.device.write({"device_name": "Should never commit"})
            raise PackingError("version_conflict", "Refresh this box.", 409)

        with self.assertRaises(HTTPException) as raised:
            service.call(rejected_operation)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "version_conflict")
        self.assertEqual(self.device.device_name, previous_name)

    def test_schemas_reject_unbound_nonfinite_and_negative_progress(self):
        base = {"quantity": 1, "version": 3, "event_id": str(uuid4()), "device_id": self.device_id}
        for changes in ({"quantity": -1}, {"quantity": 1.5}, {"quantity": float("inf")}, {"quantity": "2"}, {"quantity": True}, {"version": True}, {"event_id": "not-an-event"}, {"device_id": ""}):
            with self.assertRaises(ValidationError):
                PackingQuantityRequest(**dict(base, **changes))
        with self.assertRaises(ValidationError):
            PackingResolveRequest(device_id=self.device_id)
        with self.assertRaises(ValidationError):
            PackingResolveRequest(device_id=self.device_id, candidates=[{"barcode": "x"}] * 9)
        with self.assertRaises(ValidationError):
            PackingResolveRequest(device_id=self.device_id, barcode="another", candidates=[{"barcode": str(number)} for number in range(8)])

    def test_odoo_completion_timestamp_has_explicit_utc_meaning(self):
        detail = PackingDetail(**dict(detail_fixture(), completed_at="2026-10-05 16:00:00"))
        self.assertEqual(detail.model_dump(mode="json")["completed_at"], "2026-10-05T16:00:00Z")

    def test_multiple_visible_shipping_labels_cannot_choose_first_match(self):
        env = SimpleNamespace(cr=SimpleNamespace(savepoint=nullcontext))
        service = MobilePackingService(env, self.device_id)
        scans = PackingResolveRequest(device_id=self.device_id, candidates=[{"barcode": "label-one"}, {"barcode": "label-two"}]).scans()
        with patch.object(service, "call", side_effect=[detail_fixture(101), detail_fixture(102)]):
            # Resolve needs only a model handle here; no canonical model operation
            # or external service is invoked by this adapter-contract fixture.
            service.env = _ResolverEnvironment()
            with self.assertRaises(HTTPException) as raised:
                service.resolve(scans)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "ambiguous_label")

    def test_multiple_barcodes_for_same_box_return_selected_scan(self):
        service = MobilePackingService(_ResolverEnvironment(), self.device_id)
        scans = PackingResolveRequest(device_id=self.device_id, candidates=[{"barcode": "human-tracking", "symbology": "code128"}, {"barcode": "routing-tracking", "symbology": "code128"}]).scans()
        with patch.object(service, "call", side_effect=[detail_fixture(), detail_fixture()]):
            result = service.resolve(scans)
        self.assertEqual(result["shipment_id"], 101)
        self.assertEqual(result["resolved_barcode"], "human-tracking")


class _ResolverEnvironment:
    def __getitem__(self, key):
        return SimpleNamespace(packing_resolve=lambda *args: None)
