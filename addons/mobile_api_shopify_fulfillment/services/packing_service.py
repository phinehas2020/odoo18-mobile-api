"""Authenticated adapter; fulfillment owns all business effects and receipts."""

from fastapi import HTTPException

from odoo.exceptions import AccessError, MissingError
from odoo.addons.shopify_fulfillment.services.packing_utils import PackingError


EMPLOYEE_GROUP = "shopify_fulfillment.group_packing_employee"
SUPERVISOR_GROUP = "shopify_fulfillment.group_packing_supervisor"


def reject(code, message, status=403):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def validate_token_scope(payload, user_id, allowed_company_ids):
    """Validate against both signed claims and current user access, never defaults."""
    if not isinstance(payload, dict) or type(payload.get("uid")) is not int:
        reject("invalid_token_context", "Sign in again to use packing.", 401)
    if payload["uid"] != user_id:
        reject("invalid_token_context", "Sign in again to use packing.", 401)
    company_id = payload.get("company_id")
    token_companies = payload.get("allowed_company_ids")
    if (
        type(company_id) is not int
        or company_id <= 0
        or not isinstance(token_companies, list)
        or any(type(value) is not int for value in token_companies)
        or company_id not in token_companies
        or company_id not in allowed_company_ids
    ):
        reject("company_scope_required", "Select an authorized company and sign in again.")
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id or len(device_id) > 200:
        reject("device_binding_required", "Sign in again on this device.", 401)
    return company_id, device_id


class MobilePackingService:
    def __init__(self, env, token_device_id):
        self.env = env
        self.token_device_id = token_device_id

    def bind_device(self, requested_device_id):
        if not requested_device_id or requested_device_id != self.token_device_id:
            reject("device_mismatch", "This request belongs to a different device.")

    def capabilities(self):
        config = self.env["ir.config_parameter"].sudo()
        return {
            "enabled": str(config.get_param("fulfillment.packing_native_enabled", "false")).lower() in {"true", "1"},
            "business_enabled": str(config.get_param("fulfillment.packing_enabled", "false")).lower() in {"true", "1"},
            "can_pack": self.env.user.has_group(EMPLOYEE_GROUP),
            "can_supervise": self.env.user.has_group(SUPERVISOR_GROUP),
        }

    def authorize(self, requested_device_id, mutation=False):
        self.bind_device(requested_device_id)
        capabilities = self.capabilities()
        if not capabilities["can_pack"]:
            reject("packing_permission_required", "Packing access is required.")
        if mutation and not (capabilities["enabled"] and capabilities["business_enabled"]):
            reject("packing_disabled", "Phone packing is unavailable. Use the Odoo packing screen.", 409)

    def call(self, operation, *args, **kwargs):
        # Convert exceptions only outside the savepoint so a rejected request cannot
        # commit any partial ownership, progress, stock or accounting work.
        try:
            with self.env.cr.savepoint():
                return operation(*args, **kwargs)
        except PackingError as exc:
            reject(exc.code, exc.message, exc.status_code)
        except (AccessError, MissingError):
            reject("packing_record_unavailable", "This box is not available in your company.", 404)

    def shipment(self, shipment_id):
        shipment = self.call(self.env["fulfillment.shipment"].browse(shipment_id).exists)
        if not shipment:
            reject("packing_record_unavailable", "This box is not available in your company.", 404)
        return shipment

    def resolve(self, scans):
        matches = {}
        missing = None
        for scan in scans:
            try:
                detail = self.call(
                    self.env["fulfillment.shipment"].packing_resolve,
                    scan.barcode,
                    scan.symbology,
                )
            except HTTPException as exc:
                code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
                if code not in {"label_not_found", "unsupported_barcode", "invalid_barcode"}:
                    raise
                missing = exc
                continue
            matches.setdefault(detail["shipment_id"], (detail, scan))
        if len(matches) > 1:
            reject("ambiguous_label", "More than one shipping label is visible. Scan one box at a time.", 409)
        if not matches:
            if missing:
                raise missing
            reject("label_not_found", "No matching shipping label was found.", 404)
        detail, selected_scan = next(iter(matches.values()))
        return dict(
            detail,
            resolved_barcode=selected_scan.barcode,
            resolved_symbology=selected_scan.symbology,
        )
