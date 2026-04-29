import logging

from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class SmartLabelNotFound(Exception):
    pass


class MobileSmartLabelService:
    VALID_JOB_STATES = {"pending", "claimed", "printing", "done", "failed", "cancelled"}
    CANCEL_STATES = {"pending", "claimed", "printing"}
    RESET_STATES = {"failed", "cancelled", "done"}

    def __init__(self, env):
        self.env = env

    def list_jobs(self, state_values=None, limit=50):
        if state_values:
            invalid = sorted(set(state_values) - self.VALID_JOB_STATES)
            if invalid:
                raise UserError(f"Invalid smart label job state: {', '.join(invalid)}")
        _logger.info(
            "mobile_api.smart_label.list_jobs.start user_id=%s state=%s limit=%s",
            self.env.user.id,
            state_values,
            limit,
        )
        domain = []
        if state_values:
            domain.append(("state", "in", state_values))
        jobs = self.env["smart.label.job"].search(
            domain,
            order="requested_at desc, id desc",
            limit=limit,
        )
        _logger.info(
            "mobile_api.smart_label.list_jobs.success user_id=%s count=%s",
            self.env.user.id,
            len(jobs),
        )
        return [self.job_item(job) for job in jobs]

    def list_devices(self):
        _logger.info("mobile_api.smart_label.list_devices.start user_id=%s", self.env.user.id)
        devices = self.env["smart.label.device"].search(
            [("active", "=", True)],
            order="name, id",
        )
        _logger.info(
            "mobile_api.smart_label.list_devices.success user_id=%s count=%s",
            self.env.user.id,
            len(devices),
        )
        return [self.device_item(device) for device in devices]

    def search_products(self, query, limit=25):
        query = (query or "").strip()
        _logger.info(
            "mobile_api.smart_label.search_products.start user_id=%s query_hash=%s limit=%s",
            self.env.user.id,
            hash(query),
            limit,
        )
        product_model = self.env["product.product"]
        products = product_model.browse()
        order = "name, id" if "name" in product_model._fields else "id"
        if query:
            search_fields = [
                field_name
                for field_name in ("default_code", "barcode", "name")
                if field_name in product_model._fields
            ]
            for field_name in search_fields:
                if len(products) >= limit:
                    break
                domain = [(field_name, "ilike", query)]
                if products:
                    domain.append(("id", "not in", products.ids))
                products |= product_model.search(
                    domain,
                    order=order,
                    limit=limit - len(products),
                )

            if len(products) < limit:
                matches = product_model.name_search(
                    name=query,
                    operator="ilike",
                    limit=limit,
                )
                missing_ids = [record_id for record_id, _name in matches if record_id not in products.ids]
                if missing_ids:
                    products |= product_model.browse(missing_ids[: limit - len(products)])
        else:
            products = product_model.search([], order=order, limit=limit)

        products = products[:limit]
        profile_model = self.env["smart.label.profile"]
        _logger.info(
            "mobile_api.smart_label.search_products.success user_id=%s count=%s",
            self.env.user.id,
            len(products),
        )
        return [self.product_item(product, profile_model) for product in products]

    def queue_job(self, values):
        product_id = values.get("product_id")
        device_id = values.get("device_id")
        _logger.info(
            "mobile_api.smart_label.queue_job.start user_id=%s product_id=%s device_id=%s quantity=%s label_type=%s create_mo=%s",
            self.env.user.id,
            product_id,
            device_id,
            values.get("quantity"),
            values.get("label_type"),
            bool(values.get("create_manufacturing_order")),
        )
        product = self._find_record("product.product", product_id, "Product")

        device = self.env["smart.label.device"]
        if device_id:
            device = self._find_record("smart.label.device", device_id, "Smart label device")

        if values.get("create_manufacturing_order") and not self.env.user.has_group("mrp.group_mrp_user"):
            raise AccessError("Manufacturing order creation requires Manufacturing User access.")

        wizard_values = {
            "product_id": product.id,
            "quantity": max(int(values.get("quantity") or 1), 1),
            "label_type": values.get("label_type") or "both",
            "update_inventory": bool(values.get("update_inventory", True)),
            "create_manufacturing_order": bool(values.get("create_manufacturing_order", False)),
        }
        if device:
            wizard_values["device_id"] = device.id
        barcode = (values.get("barcode") or "").strip()
        if barcode:
            wizard_values["barcode"] = barcode
        manufacturing_user_id = values.get("manufacturing_user_id")
        if manufacturing_user_id:
            manufacturing_user = self._find_record("res.users", manufacturing_user_id, "Manufacturing user")
            wizard_values["manufacturing_user_id"] = manufacturing_user.id

        wizard = self.env["smart.label.print.wizard"].create(wizard_values)
        action = wizard.action_queue_job()
        job_id = action.get("res_id") if isinstance(action, dict) else None
        if not job_id:
            raise UserError("Smart Label job was not created.")
        job = self._find_record("smart.label.job", job_id, "Smart label job")
        _logger.info(
            "mobile_api.smart_label.queue_job.success user_id=%s job_id=%s state=%s",
            self.env.user.id,
            job.id,
            job.state,
        )
        return job

    def cancel_job(self, job_id):
        job = self._job(job_id)
        _logger.info(
            "mobile_api.smart_label.cancel_job.start user_id=%s job_id=%s state=%s",
            self.env.user.id,
            job.id,
            job.state,
        )
        if job.state not in self.CANCEL_STATES:
            raise UserError(f"Job {job.name} cannot be cancelled from state {job.state}.")
        job.action_cancel()
        _logger.info(
            "mobile_api.smart_label.cancel_job.success user_id=%s job_id=%s state=%s",
            self.env.user.id,
            job.id,
            job.state,
        )
        return job

    def reset_job(self, job_id):
        job = self._job(job_id)
        _logger.info(
            "mobile_api.smart_label.reset_job.start user_id=%s job_id=%s state=%s",
            self.env.user.id,
            job.id,
            job.state,
        )
        if job.state not in self.RESET_STATES:
            raise UserError(f"Job {job.name} cannot be reset from state {job.state}.")
        job.action_reset_to_pending()
        _logger.info(
            "mobile_api.smart_label.reset_job.success user_id=%s job_id=%s state=%s",
            self.env.user.id,
            job.id,
            job.state,
        )
        return job

    def rotate_device_token(self, device_id):
        device = self._find_record("smart.label.device", device_id, "Smart label device")
        _logger.info(
            "mobile_api.smart_label.rotate_device_token.start user_id=%s device_id=%s",
            self.env.user.id,
            device.id,
        )
        device.action_rotate_token()
        _logger.info(
            "mobile_api.smart_label.rotate_device_token.success user_id=%s device_id=%s",
            self.env.user.id,
            device.id,
        )
        return device

    def open_manufacturing_order(self, job_id):
        job = self._job(job_id)
        _logger.info(
            "mobile_api.smart_label.open_manufacturing_order.start user_id=%s job_id=%s",
            self.env.user.id,
            job.id,
        )
        if not self.env.user.has_group("mrp.group_mrp_user"):
            raise AccessError("Opening manufacturing orders requires Manufacturing User access.")
        action = job.action_open_manufacturing_order()
        if not action:
            raise SmartLabelNotFound(f"Job {job.name} does not have a manufacturing order.")
        model = action.get("res_model")
        res_id = action.get("res_id")
        if model != "mrp.production" or not res_id:
            raise UserError("Smart Label job did not return a native manufacturing order target.")
        production = self._find_record("mrp.production", res_id, "Manufacturing order")
        result = {
            "job": self.job_item(job),
            "manufacturing_order": self.manufacturing_order_item(production),
            "target": {
                "model": "mrp.production",
                "res_id": production.id,
                "native_route": f"app://manufacturing/production/{production.id}",
                "links": [
                    {
                        "rel": "gateway_record",
                        "href": f"/api/v1/gateway/models/mrp.production/records/{production.id}",
                        "method": "GET",
                    }
                ],
            },
        }
        _logger.info(
            "mobile_api.smart_label.open_manufacturing_order.success user_id=%s job_id=%s manufacturing_order_id=%s",
            self.env.user.id,
            job.id,
            production.id,
        )
        return result

    def job_item(self, job):
        return {
            "id": job.id,
            "name": job.name,
            "state": job.state,
            "product_id": job.product_id.id if job.product_id else None,
            "product_name": job.product_id.display_name if job.product_id else "Product",
            "quantity": job.quantity,
            "label_type": job.label_type,
            "requested_at": job.requested_at,
            "requested_by_name": job.requested_by.display_name if job.requested_by else None,
            "device_id": job.device_id.id if job.device_id else None,
            "device_name": job.device_id.name if job.device_id else None,
            "result_message": job.result_message,
            "manufacturing_order_id": job.manufacturing_order_id.id if job.manufacturing_order_id else None,
            "manufacturing_order_name": job.manufacturing_order_id.name if job.manufacturing_order_id else None,
        }

    def device_item(self, device):
        return {
            "id": device.id,
            "name": device.name,
            "state": device.state,
            "stock_location_name": device.stock_location_id.display_name if device.stock_location_id else None,
            "inventory_operation": device.inventory_operation,
            "last_seen_at": device.last_seen_at,
            "active": device.active,
        }

    def manufacturing_order_item(self, production):
        return {
            "id": production.id,
            "name": production.name,
            "state": production.state,
            "product_id": production.product_id.id if production.product_id else None,
            "product_name": production.product_id.display_name if production.product_id else None,
            "quantity": production.product_qty,
            "assigned_user_id": production.user_id.id if production.user_id else None,
            "assigned_user_name": production.user_id.display_name if production.user_id else None,
        }

    def product_item(self, product, profile_model):
        has_profile = bool(profile_model.search_count([("product_id", "=", product.id)]))
        return {
            "id": product.id,
            "display_name": product.display_name,
            "default_code": product.default_code,
            "barcode": product.barcode,
            "price": product.lst_price,
            "uom_name": product.uom_id.name if product.uom_id else None,
            "has_profile": has_profile,
        }

    def _job(self, job_id):
        return self._find_record("smart.label.job", job_id, "Smart label job")

    def _find_record(self, model_name, record_id, label):
        try:
            normalized_id = int(record_id or 0)
        except (TypeError, ValueError):
            normalized_id = 0
        if normalized_id <= 0:
            raise SmartLabelNotFound(f"{label} was not found.")
        record = self.env[model_name].search([("id", "=", normalized_id)], limit=1)
        if not record:
            raise SmartLabelNotFound(f"{label} {normalized_id} was not found.")
        return record
