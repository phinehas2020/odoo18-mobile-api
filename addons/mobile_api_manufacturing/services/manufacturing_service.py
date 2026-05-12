import logging
from datetime import timezone

from odoo import fields
from odoo.exceptions import AccessError, MissingError

_logger = logging.getLogger(__name__)


class MobileManufacturingService:
    def __init__(self, env):
        self.env = env

    def list_orders(self, attention="due_or_late", limit=50):
        domain = [("state", "not in", ["done", "cancel"])]
        now = fields.Datetime.now()

        if attention == "due_or_late":
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            domain.append("|")
            domain.append(("date_deadline", "<=", today_end))
            domain.append(("date_start", "<=", today_end))

        _logger.info(
            "mobile_api.manufacturing.list_orders.start user_id=%s attention=%s limit=%s",
            self.env.user.id,
            attention,
            limit,
        )
        productions = self.env["mrp.production"].search(
            domain,
            order="date_deadline asc, date_start asc, id desc",
            limit=max(min(limit or 50, 200), 1),
        )
        _logger.info(
            "mobile_api.manufacturing.list_orders.success user_id=%s count=%s domain=%s",
            self.env.user.id,
            len(productions),
            domain,
        )
        return [self.order_item(production) for production in productions]

    def list_assignees(self, limit=100):
        group = self.env.ref("mrp.group_mrp_user", raise_if_not_found=False)
        domain = [("active", "=", True), ("share", "=", False)]
        if group:
            domain.append(("groups_id", "in", [group.id]))

        _logger.info(
            "mobile_api.manufacturing.list_assignees.start user_id=%s limit=%s group_present=%s",
            self.env.user.id,
            limit,
            bool(group),
        )
        users = self.env["res.users"].search(
            domain,
            order="name asc, id asc",
            limit=max(min(limit or 100, 200), 1),
        )
        _logger.info(
            "mobile_api.manufacturing.list_assignees.success user_id=%s count=%s",
            self.env.user.id,
            len(users),
        )
        return [self.assignee_item(user) for user in users]

    def get_order(self, order_id):
        _logger.info(
            "mobile_api.manufacturing.get_order.start user_id=%s order_id=%s",
            self.env.user.id,
            order_id,
        )
        production = self.env["mrp.production"].browse(order_id).exists()
        if not production:
            _logger.warning(
                "mobile_api.manufacturing.get_order.not_found user_id=%s order_id=%s",
                self.env.user.id,
                order_id,
            )
            return None
        item = self.order_item(production)
        item.update(
            {
                "origin": self._text_or_none(production.origin),
                "bom_name": self._text_or_none(production.bom_id.display_name)
                if production.bom_id
                else None,
                "components": [
                    self.component_item(move)
                    for move in production.move_raw_ids
                    if move.product_id
                ],
                "workorders": [
                    self.workorder_item(workorder)
                    for workorder in production.workorder_ids.sorted("id")
                ],
                "quality_checks": [
                    self.quality_check_item(check)
                    for check in production.quality_check_ids.sorted("point_sequence")
                ]
                if hasattr(production, "quality_check_ids")
                else [],
            }
        )
        _logger.info(
            "mobile_api.manufacturing.get_order.success user_id=%s order_id=%s components=%s workorders=%s quality_checks=%s",
            self.env.user.id,
            order_id,
            len(item["components"]),
            len(item["workorders"]),
            len(item["quality_checks"]),
        )
        return item

    def create_order(self, payload):
        product_id = payload.get("product_id")
        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            _logger.warning(
                "mobile_api.manufacturing.create_order.product_not_found user_id=%s product_id=%s",
                self.env.user.id,
                product_id,
            )
            return None

        assigned_user = self._assigned_user(payload.get("assigned_user_id"))
        quantity = max(float(payload.get("quantity") or 1), 1.0)
        values = {
            "product_id": product.id,
            "product_qty": quantity,
            "product_uom_id": product.uom_id.id,
            "date_deadline": self._odoo_datetime_or_false(payload.get("deadline")),
            "user_id": assigned_user.id,
        }
        notes = self._text_or_none(payload.get("notes"))
        if notes:
            values["origin"] = notes[:200]

        _logger.info(
            "mobile_api.manufacturing.create_order.start user_id=%s product_id=%s quantity=%s assigned_user_id=%s deadline_present=%s",
            self.env.user.id,
            product.id,
            quantity,
            assigned_user.id,
            bool(values["date_deadline"]),
        )
        production = self.env["mrp.production"].create(values)
        production.action_confirm()
        if notes:
            production.message_post(body=notes)
        _logger.info(
            "mobile_api.manufacturing.create_order.success user_id=%s order_id=%s name=%s",
            self.env.user.id,
            production.id,
            production.name,
        )
        return self.order_item(production)

    def plan_order(self, order_id):
        production = self._production(order_id)
        _logger.info(
            "mobile_api.manufacturing.plan_order.start user_id=%s order_id=%s state=%s is_planned=%s",
            self.env.user.id,
            production.id,
            production.state,
            production.is_planned,
        )
        production.button_plan()
        _logger.info(
            "mobile_api.manufacturing.plan_order.success user_id=%s order_id=%s workorders=%s",
            self.env.user.id,
            production.id,
            len(production.workorder_ids),
        )
        return self.get_order(production.id)

    def start_workorder(self, workorder_id):
        workorder = self._workorder(workorder_id)
        _logger.info(
            "mobile_api.manufacturing.start_workorder.start user_id=%s workorder_id=%s state=%s",
            self.env.user.id,
            workorder.id,
            workorder.state,
        )
        workorder.button_start()
        return self.get_order(workorder.production_id.id)

    def stop_workorder(self, workorder_id):
        workorder = self._workorder(workorder_id)
        _logger.info(
            "mobile_api.manufacturing.stop_workorder.start user_id=%s workorder_id=%s state=%s",
            self.env.user.id,
            workorder.id,
            workorder.state,
        )
        workorder.button_pending()
        return self.get_order(workorder.production_id.id)

    def finish_workorder(self, workorder_id):
        workorder = self._workorder(workorder_id)
        _logger.info(
            "mobile_api.manufacturing.finish_workorder.start user_id=%s workorder_id=%s state=%s",
            self.env.user.id,
            workorder.id,
            workorder.state,
        )
        workorder.button_finish()
        return self.get_order(workorder.production_id.id)

    def pass_quality_check(self, check_id, notes=None):
        check = self._quality_check(check_id)
        self._write_quality_notes(check, notes)
        _logger.info(
            "mobile_api.manufacturing.pass_quality_check.start user_id=%s check_id=%s state=%s",
            self.env.user.id,
            check.id,
            check.state,
        )
        check.action_pass()
        return self.get_order(check.production_id.id)

    def fail_quality_check(self, check_id, notes=None):
        check = self._quality_check(check_id)
        self._write_quality_notes(check, notes)
        _logger.info(
            "mobile_api.manufacturing.fail_quality_check.start user_id=%s check_id=%s state=%s",
            self.env.user.id,
            check.id,
            check.state,
        )
        check.action_fail()
        return self.get_order(check.production_id.id)

    def complete_order(self, order_id):
        production = self._production(order_id)

        _logger.info(
            "mobile_api.manufacturing.complete_order.start user_id=%s order_id=%s state=%s",
            self.env.user.id,
            production.id,
            production.state,
        )
        if production.state == "draft":
            production.action_confirm()
        if production.state not in ("done", "cancel"):
            production.qty_producing = production.product_qty
            for move in production.move_raw_ids:
                if hasattr(move, "quantity"):
                    move.quantity = move.product_uom_qty
                elif hasattr(move, "quantity_done"):
                    move.quantity_done = move.product_uom_qty
            production.button_mark_done()
        _logger.info(
            "mobile_api.manufacturing.complete_order.success user_id=%s order_id=%s state=%s",
            self.env.user.id,
            production.id,
            production.state,
        )
        return self.get_order(production.id)

    def order_item(self, production):
        return {
            "id": production.id,
            "name": self._text_or_none(production.name) or f"MO {production.id}",
            "state": self._text_or_none(production.state) or "unknown",
            "product_id": production.product_id.id if production.product_id else None,
            "product_name": self._text_or_none(production.product_id.display_name)
            if production.product_id
            else None,
            "quantity": production.product_qty,
            "uom_name": self._text_or_none(production.product_uom_id.name)
            if production.product_uom_id
            else None,
            "planned_date": self._datetime_or_none(production.date_start),
            "deadline": self._datetime_or_none(production.date_deadline),
            "assigned_user_name": self._text_or_none(production.user_id.display_name)
            if production.user_id
            else None,
            "is_planned": bool(production.is_planned),
            "quality_state": self._text_or_none(getattr(production, "quality_state", None)),
            "quality_check_count": len(production.quality_check_ids)
            if hasattr(production, "quality_check_ids")
            else 0,
            "attention_reason": self._attention_reason(production),
        }

    def assignee_item(self, user):
        return {
            "id": user.id,
            "name": self._text_or_none(user.display_name)
            or self._text_or_none(user.name)
            or f"User {user.id}",
            "login": self._text_or_none(user.login),
            "email": self._text_or_none(user.email),
        }

    def workorder_item(self, workorder):
        return {
            "id": workorder.id,
            "name": self._text_or_none(workorder.name) or f"Step {workorder.id}",
            "state": self._text_or_none(workorder.state) or "unknown",
            "workcenter_name": self._text_or_none(workorder.workcenter_id.display_name)
            if workorder.workcenter_id
            else None,
            "product_name": self._text_or_none(workorder.product_id.display_name)
            if workorder.product_id
            else None,
            "quantity": self._number_or_none(getattr(workorder, "qty_production", None)),
            "quantity_remaining": self._number_or_none(
                getattr(workorder, "qty_remaining", None)
            ),
            "expected_duration_minutes": self._number_or_none(
                getattr(workorder, "duration_expected", None)
            ),
            "real_duration_minutes": self._number_or_none(
                getattr(workorder, "duration", None)
            ),
            "is_user_working": bool(getattr(workorder, "is_user_working", False)),
            "working_state": self._text_or_none(getattr(workorder, "working_state", None)),
            "started_at": self._datetime_or_none(workorder.date_start),
            "finished_at": self._datetime_or_none(workorder.date_finished),
        }

    def quality_check_item(self, check):
        return {
            "id": check.id,
            "name": self._text_or_none(check.name) or f"Quality Check {check.id}",
            "state": self._text_or_none(check.state) or "pending",
            "control_type": self._text_or_none(check.control_type),
            "failure_action": self._text_or_none(check.failure_action),
            "notes": self._text_or_none(check.notes),
            "instructions": self._text_or_none(check.instructions),
            "completed_by_name": self._text_or_none(check.completed_by.display_name)
            if check.completed_by
            else None,
            "completed_date": self._datetime_or_none(check.completed_date),
        }

    def component_item(self, move):
        return {
            "id": move.id,
            "product_id": move.product_id.id if move.product_id else None,
            "product_name": self._text_or_none(move.product_id.display_name)
            or f"Product {move.product_id.id if move.product_id else move.id}",
            "quantity": move.product_uom_qty,
            "reserved_quantity": self._number_or_none(
                getattr(move, "reserved_availability", None)
            ),
            "done_quantity": self._number_or_none(
                getattr(move, "quantity_done", None)
            ),
            "uom_name": self._text_or_none(move.product_uom.name)
            if move.product_uom
            else None,
        }

    def _attention_reason(self, production):
        now = fields.Datetime.now()
        deadline = production.date_deadline
        planned_date = production.date_start
        if deadline and deadline < now:
            return "overdue"
        if deadline and deadline.date() == now.date():
            return "due_today"
        if planned_date and planned_date < now:
            return "planned_overdue"
        if planned_date and planned_date.date() == now.date():
            return "planned_today"
        return None

    def _assigned_user(self, user_id):
        if not user_id:
            return self.env.user

        user = self.env["res.users"].browse(user_id).exists()
        if not user:
            raise MissingError("Assigned employee was not found.")
        if not user.active or user.share:
            raise AccessError("Assigned employee must be an active internal Odoo user.")

        group = self.env.ref("mrp.group_mrp_user", raise_if_not_found=False)
        if group and group not in user.groups_id:
            raise AccessError("Assigned employee must have manufacturing access.")
        return user

    def _production(self, order_id):
        production = self.env["mrp.production"].browse(order_id).exists()
        if not production:
            raise MissingError("Manufacturing order was not found.")
        return production

    def _workorder(self, workorder_id):
        workorder = self.env["mrp.workorder"].browse(workorder_id).exists()
        if not workorder:
            raise MissingError("Work order step was not found.")
        return workorder

    def _quality_check(self, check_id):
        check = self.env["hg.quality.check"].browse(check_id).exists()
        if not check:
            raise MissingError("Quality check was not found.")
        return check

    def _write_quality_notes(self, check, notes):
        notes = self._text_or_none(notes)
        if notes:
            check.write({"notes": notes})

    def _text_or_none(self, value):
        if isinstance(value, str) and value:
            return value
        return None

    def _datetime_or_none(self, value):
        if not value:
            return None
        if value.tzinfo:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)

    def _odoo_datetime_or_false(self, value):
        if not value:
            return False
        if getattr(value, "tzinfo", None):
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        parsed = fields.Datetime.to_datetime(value)
        if not parsed:
            return False
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _number_or_none(self, value):
        if value is False or value is None:
            return None
        return value
