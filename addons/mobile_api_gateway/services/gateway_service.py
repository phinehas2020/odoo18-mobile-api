import json
import logging
from datetime import date, datetime

from odoo.exceptions import AccessError, UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class GatewayAccessError(Exception):
    pass


class GatewayNotFound(Exception):
    pass


class GatewayBadRequest(Exception):
    pass


class MobileGatewayService:
    DEFAULT_MODEL_ALLOWLIST = {
        "calendar.event",
        "crm.lead",
        "fleet.vehicle",
        "hr.employee",
        "maintenance.request",
        "mrp.production",
        "product.product",
        "product.template",
        "project.project",
        "project.task",
        "purchase.order",
        "repair.order",
        "res.partner",
        "sale.order",
        "smart.label.device",
        "smart.label.job",
        "smart.label.profile",
        "stock.location",
        "stock.move",
        "stock.move.line",
        "stock.picking",
    }
    BLOCKED_PREFIXES = ("ir.", "base.")
    BLOCKED_MODELS = {
        "res.users",
        "res.groups",
        "res.config.settings",
        "ir.config_parameter",
        "ir.attachment",
        "mail.message",
        "mail.mail",
    }
    SAFE_FIELD_TYPES = {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "html",
        "integer",
        "many2many",
        "many2one",
        "monetary",
        "one2many",
        "selection",
        "text",
    }
    SEARCHABLE_TYPES = {"char", "text", "html", "selection"}
    DEFAULT_SUMMARY_FIELD_CANDIDATES = (
        "display_name",
        "name",
        "state",
        "default_code",
        "barcode",
        "partner_id",
        "product_id",
        "amount_total",
        "quantity",
        "product_uom_qty",
        "write_date",
    )

    def __init__(self, env):
        self.env = env
        self.config = env["ir.config_parameter"].sudo()

    def manifest(self):
        models = self.models()
        return {
            "version": "1",
            "user_id": self.env.user.id,
            "company_id": self.env.company.id if self.env.company else None,
            "models": models,
            "workflows": self.workflows(models),
            "links": [
                self._link("models", "/api/v1/gateway/models"),
            ],
        }

    def models(self, search=None):
        summaries = [self.model_summary(model_name) for model_name in sorted(self.available_model_names())]
        summaries = [summary for summary in summaries if summary]
        if search:
            lowered = search.lower()
            summaries = [
                summary for summary in summaries
                if lowered in summary["model"].lower() or lowered in summary["label"].lower()
            ]
        return summaries

    def workflows(self, model_summaries):
        by_model = {item["model"]: item for item in model_summaries}
        workflows = []
        known = [
            ("inventory", "Inventory", "stock.picking", "app://inventory"),
            ("sales", "Sales", "sale.order", "app://sales"),
            ("products", "Products", "product.product", "app://products"),
            ("contacts", "Contacts", "res.partner", "app://contacts"),
            ("manufacturing", "Manufacturing", "mrp.production", "app://manufacturing"),
            ("maintenance", "Maintenance", "maintenance.request", "app://maintenance"),
            ("repairs", "Repairs", "repair.order", "app://repairs"),
            ("smart-labels", "Smart Labels", "smart.label.job", "app://smart-labels"),
        ]
        for key, label, model, route in known:
            if model in by_model:
                links = [self._link("records", f"/api/v1/gateway/models/{model}/records")]
                if key == "smart-labels" and self._module_installed("mobile_api_smart_label"):
                    links.extend([
                        self._link("queue_job", "/api/v1/smart-label/jobs", "POST"),
                        self._link("cancel_job", "/api/v1/smart-label/jobs/{job_id}/cancel", "POST"),
                        self._link("reset_job", "/api/v1/smart-label/jobs/{job_id}/reset", "POST"),
                        self._link(
                            "open_manufacturing_order",
                            "/api/v1/smart-label/jobs/{job_id}/open-manufacturing-order",
                            "POST",
                        ),
                        self._link(
                            "rotate_device_token",
                            "/api/v1/smart-label/devices/{device_id}/rotate-token",
                            "POST",
                        ),
                    ])
                if key == "manufacturing" and self._module_installed("mobile_api_manufacturing"):
                    links.extend([
                        self._link("attention_orders", "/api/v1/manufacturing/orders?attention=due_or_late"),
                        self._link("order_detail", "/api/v1/manufacturing/orders/{order_id}"),
                    ])
                workflows.append({
                    "key": key,
                    "label": label,
                    "model": model,
                    "native_route": route,
                    "links": links,
                })
        return workflows

    def model_detail(self, model_name):
        self._assert_model_allowed(model_name, "read")
        summary = self.model_summary(model_name)
        if not summary:
            raise GatewayNotFound(f"Model {model_name} is not available")
        fields = self._safe_fields(model_name)
        return {
            **summary,
            "fields": list(fields.values()),
            "default_list_fields": self._default_list_fields(model_name, fields),
            "default_detail_fields": list(fields.keys())[:80],
        }

    def list_records(self, model_name, search=None, domain_json=None, field_csv=None, order=None, limit=40, offset=0):
        model = self._model(model_name, "read")
        domain = self._decode_domain(domain_json)
        domain = self._apply_search_domain(model, domain, search)
        fields = self._requested_fields(model_name, field_csv, detail=False)
        try:
            total = model.search_count(domain)
            records = model.search(domain, order=order or self._default_order(model), limit=limit, offset=offset)
        except AccessError as exc:
            raise GatewayAccessError(str(exc))
        except UserError as exc:
            raise GatewayBadRequest(str(exc))
        except (TypeError, ValueError) as exc:
            raise GatewayBadRequest(f"Invalid gateway query for {model_name}: {exc}")
        return {
            "model": model_name,
            "total": total,
            "limit": limit,
            "offset": offset,
            "records": self._read_records(records, fields),
            "links": [self._link("model", f"/api/v1/gateway/models/{model_name}")],
        }

    def get_record(self, model_name, record_id, field_csv=None):
        model = self._model(model_name, "read")
        record = model.browse(record_id).exists()
        if not record:
            raise GatewayNotFound(f"Record {record_id} was not found in {model_name}")
        fields = self._requested_fields(model_name, field_csv, detail=True)
        payload = self._read_records(record, fields)
        if not payload:
            raise GatewayNotFound(f"Record {record_id} was not readable in {model_name}")
        return {
            "model": model_name,
            "id": record.id,
            "record": payload[0],
            "links": [self._link("records", f"/api/v1/gateway/models/{model_name}/records")],
        }

    def create_record(self, model_name, values):
        model = self._model(model_name, "create")
        self._assert_write_enabled(model_name, "create")
        safe_values = self._safe_write_values(model_name, values)
        try:
            record = model.create(safe_values)
        except (AccessError, UserError) as exc:
            raise GatewayAccessError(str(exc))
        return self.get_record(model_name, record.id)

    def update_record(self, model_name, record_id, values):
        model = self._model(model_name, "write")
        self._assert_write_enabled(model_name, "write")
        record = model.browse(record_id).exists()
        if not record:
            raise GatewayNotFound(f"Record {record_id} was not found in {model_name}")
        safe_values = self._safe_write_values(model_name, values)
        try:
            record.write(safe_values)
        except (AccessError, UserError) as exc:
            raise GatewayAccessError(str(exc))
        return self.get_record(model_name, record.id)

    def call_method(self, model_name, record_id, method_name, args=None, kwargs=None):
        self._model(model_name, "read")
        if f"{model_name}.{method_name}" not in self._configured_set("mobile_api_gateway.allowed_methods"):
            raise GatewayAccessError(f"Method {model_name}.{method_name} is not enabled for mobile")
        record = self.env[model_name].browse(record_id).exists()
        if not record:
            raise GatewayNotFound(f"Record {record_id} was not found in {model_name}")
        if method_name.startswith("_") or not hasattr(record, method_name):
            raise GatewayNotFound(f"Method {method_name} was not found on {model_name}")
        method = getattr(record, method_name)
        try:
            result = method(*(args or []), **(kwargs or {}))
        except (AccessError, UserError) as exc:
            raise GatewayAccessError(str(exc))
        return {
            "model": model_name,
            "id": record_id,
            "method": method_name,
            "result": self._json_safe(result),
        }

    def available_model_names(self):
        names = set(self.DEFAULT_MODEL_ALLOWLIST)
        names.update(self._configured_set("mobile_api_gateway.extra_models"))
        names.update(self._menu_action_model_names())
        names.difference_update(self._configured_set("mobile_api_gateway.blocked_models"))
        return {name for name in names if self._is_model_available(name)}

    def model_summary(self, model_name):
        if not self._is_model_available(model_name):
            return None
        model = self.env[model_name]
        ir_model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
        return {
            "model": model_name,
            "label": ir_model.name or getattr(model, "_description", model_name) or model_name,
            "module": self._module_for_model(ir_model),
            "read": model.check_access_rights("read", raise_exception=False),
            "create": self._can_write(model_name, "create"),
            "write": self._can_write(model_name, "write"),
            "actions": self._configured_methods_for_model(model_name),
            "links": [
                self._link("detail", f"/api/v1/gateway/models/{model_name}"),
                self._link("records", f"/api/v1/gateway/models/{model_name}/records"),
            ],
        }

    def _menu_action_model_names(self):
        names = set()
        menus = self.env["ir.ui.menu"].search([])
        for menu in menus:
            action = menu.action
            if action and getattr(action, "res_model", None):
                names.add(action.res_model)
        return names

    def _is_model_available(self, model_name):
        if not model_name or model_name in self.BLOCKED_MODELS:
            return False
        if any(model_name.startswith(prefix) for prefix in self.BLOCKED_PREFIXES):
            return False
        try:
            model = self.env[model_name]
        except KeyError:
            return False
        if getattr(model, "_abstract", False) or getattr(model, "_transient", False):
            return False
        return model.check_access_rights("read", raise_exception=False)

    def _model(self, model_name, operation="read"):
        self._assert_model_allowed(model_name, operation)
        return self.env[model_name]

    def _assert_model_allowed(self, model_name, operation="read"):
        if not self._is_model_available(model_name):
            raise GatewayAccessError(f"Model {model_name} is not available for mobile")
        model = self.env[model_name]
        if not model.check_access_rights(operation, raise_exception=False):
            raise GatewayAccessError(f"No {operation} access for {model_name}")

    def _assert_write_enabled(self, model_name, operation):
        configured = self._configured_set(f"mobile_api_gateway.{operation}_models")
        if model_name not in configured:
            raise GatewayAccessError(f"{operation.title()} is not enabled for {model_name} on mobile")

    def _can_write(self, model_name, operation):
        if model_name not in self._configured_set(f"mobile_api_gateway.{operation}_models"):
            return False
        try:
            return self.env[model_name].check_access_rights(operation, raise_exception=False)
        except KeyError:
            return False

    def _safe_fields(self, model_name):
        model = self.env[model_name]
        raw_fields = model.fields_get()
        safe = {}
        readable_names = self._field_access(model, "read", list(raw_fields.keys()))
        for name, info in raw_fields.items():
            field_type = info.get("type")
            if name not in readable_names or field_type not in self.SAFE_FIELD_TYPES:
                continue
            if info.get("groups"):
                continue
            safe[name] = {
                "name": name,
                "label": info.get("string") or name,
                "type": field_type,
                "required": bool(info.get("required")),
                "readonly": bool(info.get("readonly")),
                "relation": info.get("relation"),
                "selection": self._safe_selection(info.get("selection")),
                "searchable": field_type in self.SEARCHABLE_TYPES,
            }
        if "display_name" not in safe:
            safe["display_name"] = {
                "name": "display_name",
                "label": "Display Name",
                "type": "char",
                "required": False,
                "readonly": True,
                "relation": None,
                "selection": None,
                "searchable": True,
            }
        return safe

    def _field_access(self, model, operation, field_names):
        checker = getattr(model, "check_field_access_rights", None)
        if not checker:
            return set(field_names)
        try:
            return set(checker(operation, field_names))
        except AccessError:
            return set()

    def _requested_fields(self, model_name, field_csv=None, detail=False):
        fields = self._safe_fields(model_name)
        if field_csv:
            requested = [item.strip() for item in field_csv.split(",") if item.strip()]
        elif detail:
            requested = list(fields.keys())[:80]
        else:
            requested = self._default_list_fields(model_name, fields)
        selected = [name for name in requested if name in fields]
        if "display_name" not in selected:
            selected.insert(0, "display_name")
        return selected[:100]

    def _default_list_fields(self, model_name, fields):
        selected = [name for name in self.DEFAULT_SUMMARY_FIELD_CANDIDATES if name in fields]
        if len(selected) < 5:
            selected.extend([name for name in fields.keys() if name not in selected][: 5 - len(selected)])
        return selected[:12]

    def _read_records(self, records, field_names):
        if not records:
            return []
        read_fields = [name for name in field_names if name != "display_name"]
        try:
            rows = records.read(read_fields) if read_fields else [{"id": record.id} for record in records]
        except AccessError as exc:
            raise GatewayAccessError(str(exc))
        by_id = {record.id: record for record in records}
        for row in rows:
            record = by_id.get(row.get("id"))
            if record:
                row["display_name"] = record.display_name
        return [self._json_safe(row) for row in rows]

    def _safe_write_values(self, model_name, values):
        if not isinstance(values, dict):
            raise GatewayBadRequest("values must be an object")
        fields = self._safe_fields(model_name)
        writable_names = self._field_access(self.env[model_name], "write", list(fields.keys()))
        safe = {}
        for name, value in values.items():
            field = fields.get(name)
            if not field or field.get("readonly") or name not in writable_names:
                continue
            if field["type"] in {"one2many", "many2many", "binary"}:
                continue
            safe[name] = value
        if not safe:
            raise GatewayBadRequest("No writable mobile-safe fields were provided")
        return safe

    def _decode_domain(self, domain_json):
        if not domain_json:
            return []
        try:
            domain = json.loads(domain_json)
        except ValueError as exc:
            raise GatewayBadRequest(f"Invalid domain JSON: {exc}")
        if not isinstance(domain, list):
            raise GatewayBadRequest("Domain must be a JSON list")
        return domain

    def _apply_search_domain(self, model, domain, search):
        if not search:
            return domain
        fields = self._safe_fields(model._name)
        candidates = []
        seen = set()
        for name in (model._rec_name, "name", "default_code", "barcode", "email", "phone", "display_name"):
            if not name or name in seen:
                continue
            seen.add(name)
            if name in fields and fields[name]["searchable"] and name != "display_name":
                candidates.append((name, "ilike", search))
        if not candidates:
            return domain
        return expression.AND([domain, expression.OR(candidates)])

    def _default_order(self, model):
        order = getattr(model, "_order", None)
        return order or "id desc"

    def _safe_selection(self, selection):
        if not selection or not isinstance(selection, (list, tuple)):
            return None
        return [[item[0], item[1]] for item in selection if isinstance(item, (list, tuple)) and len(item) >= 2]

    def _module_for_model(self, ir_model):
        if not ir_model:
            return None
        modules = ir_model.modules
        if not modules:
            return None
        return modules.split(",")[0].strip()

    def _module_installed(self, module_name):
        return bool(
            self.env["ir.module.module"]
            .sudo()
            .search([("name", "=", module_name), ("state", "=", "installed")], limit=1)
        )

    def _configured_set(self, key):
        value = self.config.get_param(key, "") or ""
        return {item.strip() for item in value.split(",") if item.strip()}

    def _configured_methods_for_model(self, model_name):
        prefix = f"{model_name}."
        return sorted(item[len(prefix):] for item in self._configured_set("mobile_api_gateway.allowed_methods") if item.startswith(prefix))

    def _link(self, rel, href, method="GET"):
        return {"rel": rel, "href": href, "method": method}

    def _json_safe(self, value):
        if isinstance(value, dict):
            return {key: self._json_safe(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if hasattr(value, "ids"):
            return value.ids
        return value
