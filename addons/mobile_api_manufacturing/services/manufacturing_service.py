import logging
import base64
import binascii
from datetime import timezone

from odoo import fields
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class MobileManufacturingService:
    def __init__(self, env):
        self.env = env

    def list_orders(self, attention="due_or_late", limit=50):
        self._require_quality_access("read")
        domain = [("state", "not in", ["done", "cancel"])]
        # The mobile work list follows the MO responsible user, not its creator.
        # Settings administrators retain the cross-user overview, under normal ACLs.
        if not self.env.user.has_group("base.group_system"):
            domain.append(("user_id", "=", self.env.user.id))
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

    def list_products(self, search=None, limit=50):
        domain = [("type", "=", "consu"), ("active", "=", True)]
        if search:
            domain.append(("display_name", "ilike", search.strip()))
        products = self.env["product.product"].search(
            domain, order="name asc, id asc", limit=max(min(limit or 50, 200), 1)
        )
        return [
            {
                "id": product.id,
                "name": product.display_name,
                "tracking": product.tracking or "none",
                "uom_name": product.uom_id.name if product.uom_id else None,
            }
            for product in products
        ]

    def list_product_lots(self, product_id, search=None, limit=50):
        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            raise MissingError("Product was not found.")
        domain = [("product_id", "=", product.id), ("company_id", "in", [False, self.env.company.id])]
        if search:
            domain.append(("name", "ilike", search.strip()))
        lots = self.env["stock.lot"].search(
            domain, order="name asc, id asc", limit=max(min(limit or 50, 200), 1)
        )
        return [{"id": lot.id, "name": lot.name} for lot in lots]

    def get_order(self, order_id):
        self._require_quality_access("read")
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
                if "quality_check_ids" in production._fields
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
        quantity = float(payload.get("quantity") or 1)
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
        if production.state == "draft":
            production.action_confirm()
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
        blocking_checks = workorder.production_id.quality_check_ids.filtered(
            lambda check: check.point_id.workcenter_id == workorder.workcenter_id
            and check.failure_action == "block"
            and check.state != "pass"
        )
        if blocking_checks:
            raise UserError(
                "Complete the required quality checks for this work center before finishing the step."
            )
        workorder.button_finish()
        return self.get_order(workorder.production_id.id)

    def pass_quality_check(self, check_id, notes=None):
        check = self._quality_check(check_id)
        if check.control_type == "picture":
            raise UserError("Photo quality checks must be completed in Odoo with the required photo.")
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
        if check.control_type != "passfail":
            raise UserError("Only Pass / Fail quality checks can be failed from mobile.")
        self._write_quality_notes(check, notes)
        _logger.info(
            "mobile_api.manufacturing.fail_quality_check.start user_id=%s check_id=%s state=%s",
            self.env.user.id,
            check.id,
            check.state,
        )
        check.action_fail()
        return self.get_order(check.production_id.id)

    def submit_quality_photo(self, check_id, image_base64, filename, notes=None):
        check = self._quality_check(check_id)
        if check.control_type != "picture":
            raise ValidationError("This quality check does not accept photo evidence.")
        try:
            image = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError("Photo evidence must be valid base64.")
        if not image or len(image) > 5 * 1024 * 1024:
            raise ValidationError("Photo evidence must be 5 MB or smaller.")
        if not (image.startswith(b"\xff\xd8\xff") or image.startswith(b"\x89PNG\r\n\x1a\n")):
            raise ValidationError("Photo evidence must be a JPEG or PNG image.")
        safe_filename = (self._text_or_none(filename) or "quality-check.jpg").rsplit("/", 1)[-1]
        check.write(
            {
                "picture": base64.b64encode(image),
                "picture_filename": safe_filename[:150],
            }
        )
        self._write_quality_notes(check, notes)
        check.action_pass()
        return self.get_order(check.production_id.id)

    def completion_review(self, order_id):
        self._require_quality_access("read")
        production = self._production(order_id)
        remaining = self._quantity_remaining(production)
        open_workorders = production.workorder_ids.filtered(
            lambda workorder: workorder.state not in ("done", "cancel")
        )
        quality_checks = (
            production.quality_check_ids
            if "quality_check_ids" in production._fields
            else []
        )
        pending_quality = quality_checks.filtered(
            lambda check: check.state == "pending"
            or (check.state == "fail" and check.failure_action == "block")
        ) if quality_checks else []
        blockers = []
        if production.state in ("done", "cancel"):
            blockers.append("This manufacturing order is already closed.")
        if production.state == "draft":
            blockers.append("Confirm or plan this manufacturing order before completion.")
        if float_is_zero(remaining, precision_rounding=production.product_uom_id.rounding):
            blockers.append("No quantity remains to produce.")
        if open_workorders:
            blockers.append("Finish or cancel every work order step before completion.")
        if pending_quality:
            blockers.append("Resolve every quality check before completion.")
        warnings = []
        for move in production.move_raw_ids.filtered(lambda move: move.state not in ("done", "cancel")):
            if float_compare(
                self._move_done_quantity(move),
                move.product_uom_qty,
                precision_rounding=move.product_uom.rounding,
            ) != 0:
                warnings.append(
                    f"Review {move.product_id.display_name}: recorded consumption differs from the planned quantity."
                )
        return {
            "order_id": production.id,
            "can_complete": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "suggested_quantity": remaining,
            "quantity_remaining": remaining,
            "requires_finished_lot": production.product_id.tracking != "none",
            "open_workorder_ids": open_workorders.ids,
            "pending_quality_check_ids": pending_quality.ids if pending_quality else [],
        }

    def complete_order(self, order_id, payload):
        production = self._production(order_id)
        production.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM mrp_production WHERE id = %s FOR UPDATE",
            [production.id],
        )
        production.invalidate_recordset()

        _logger.info(
            "mobile_api.manufacturing.complete_order.start user_id=%s order_id=%s state=%s",
            self.env.user.id,
            production.id,
            production.state,
        )
        if not payload.get("reviewed"):
            raise ValidationError("Completion must be reviewed before it is submitted.")
        review = self.completion_review(production.id)
        if review["blockers"]:
            raise UserError(" ".join(review["blockers"]))

        quantity = float(payload.get("quantity") or 0)
        if float_compare(quantity, 0, precision_rounding=production.product_uom_id.rounding) <= 0:
            raise ValidationError("Produced quantity must be greater than zero.")
        if float_compare(
            quantity,
            review["quantity_remaining"],
            precision_rounding=production.product_uom_id.rounding,
        ) > 0:
            raise ValidationError("Produced quantity cannot exceed the remaining quantity.")
        disposition = payload.get("disposition")
        if disposition not in ("close", "backorder"):
            raise ValidationError("Disposition must be close or backorder.")
        if disposition == "backorder" and float_compare(
            quantity,
            review["quantity_remaining"],
            precision_rounding=production.product_uom_id.rounding,
        ) >= 0:
            raise ValidationError("A backorder requires a produced quantity below the remaining quantity.")

        with self.env.cr.savepoint():
            production.qty_producing = quantity
            self._set_finished_lot(production, payload)
            self._set_component_consumption(production, payload.get("components") or [])
            context = {"skip_consumption": True, "skip_backorder": True, "skip_redirection": True}
            if disposition == "backorder":
                context["mo_ids_to_backorder"] = [production.id]
            result = production.with_context(**context).button_mark_done()
            if result is not True:
                raise UserError(
                    "Odoo requires another manufacturing review step; complete this order in Odoo."
                )
            if production.state != "done":
                raise UserError("Odoo did not mark the manufacturing order done.")
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
            if "quality_check_ids" in production._fields
            else 0,
            "attention_reason": self._attention_reason(production),
            "quantity_producing": self._number_or_none(production.qty_producing),
            "quantity_remaining": self._quantity_remaining(production),
            "product_tracking": production.product_id.tracking or "none",
            "finished_lot_id": production.lot_producing_id.id
            if production.lot_producing_id
            else None,
            "finished_lot_name": self._text_or_none(production.lot_producing_id.name)
            if production.lot_producing_id
            else None,
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
        employee = getattr(workorder, "employee_id", None)
        is_user_working = bool(
            workorder.time_ids.filtered(
                lambda time: not time.date_end and time.user_id.id == self.env.user.id
            )
        ) or bool(getattr(workorder, "is_user_working", False))
        return {
            "id": workorder.id,
            "name": self._text_or_none(workorder.name) or f"Step {workorder.id}",
            "state": self._text_or_none(workorder.state) or "unknown",
            "employee_name": self._text_or_none(employee.display_name) if employee else None,
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
            "is_user_working": is_user_working,
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
            "has_photo": bool(check.picture),
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
            "done_quantity": self._move_done_quantity(move),
            "uom_name": self._text_or_none(move.product_uom.name)
            if move.product_uom
            else None,
            "tracking": move.product_id.tracking or "none",
            "picked": bool(move.picked),
            "lot_quantities": [
                {
                    "lot_id": line.lot_id.id if line.lot_id else None,
                    "lot_name": self._text_or_none(line.lot_id.name or line.lot_name),
                    "quantity": line.product_uom_id._compute_quantity(
                        line.quantity, move.product_uom, round=False
                    ),
                }
                for line in move.move_line_ids
                if not float_is_zero(line.quantity, precision_rounding=line.product_uom_id.rounding)
            ],
        }

    def _set_finished_lot(self, production, payload):
        lot_id = payload.get("finished_lot_id")
        lot_name = self._text_or_none(payload.get("finished_lot_name"))
        lot_name = lot_name.strip() if lot_name else None
        if lot_id and lot_name:
            raise ValidationError("Choose an existing finished lot or enter a new lot name, not both.")
        if production.product_id.tracking == "none":
            if lot_id or lot_name:
                raise ValidationError("The finished product is not lot tracked.")
            return
        if not lot_id and not lot_name:
            raise ValidationError("A finished lot or serial number is required.")
        if production.product_id.tracking == "serial" and float_compare(
            production.qty_producing,
            1,
            precision_rounding=production.product_uom_id.rounding,
        ) != 0:
            raise ValidationError("A serial-tracked completion must produce exactly one unit.")
        if lot_id:
            lot = self.env["stock.lot"].browse(lot_id).exists()
            if not lot or lot.product_id != production.product_id:
                raise ValidationError("The finished lot does not belong to this product.")
        else:
            lot = self.env["stock.lot"].search(
                [
                    ("name", "=", lot_name),
                    ("product_id", "=", production.product_id.id),
                    ("company_id", "=", production.company_id.id),
                ],
                limit=1,
            )
            if not lot:
                lot = self.env["stock.lot"].create(
                    {
                        "name": lot_name,
                        "product_id": production.product_id.id,
                        "company_id": production.company_id.id,
                    }
                )
        production.lot_producing_id = lot

    def _set_component_consumption(self, production, allocations):
        moves = production.move_raw_ids.filtered(lambda move: move.state not in ("done", "cancel"))
        move_by_id = {move.id: move for move in moves}
        grouped = {move.id: [] for move in moves}
        seen_lot_allocations = set()
        for allocation in allocations:
            move_id = allocation.get("move_id")
            if move_id not in move_by_id:
                raise ValidationError(f"Component move {move_id} does not belong to this order.")
            lot_id = allocation.get("lot_id")
            allocation_key = (move_id, lot_id)
            if lot_id and allocation_key in seen_lot_allocations:
                raise ValidationError("Each component lot may appear only once per move.")
            if lot_id:
                seen_lot_allocations.add(allocation_key)
            grouped[move_id].append(allocation)
        missing = [move.product_id.display_name for move in moves if not grouped[move.id]]
        if missing:
            raise ValidationError("Explicit quantities are required for every component: " + ", ".join(missing))

        for move in moves:
            rows = grouped[move.id]
            tracking = move.product_id.tracking or "none"
            if tracking == "none":
                if len(rows) != 1 or rows[0].get("lot_id"):
                    raise ValidationError(
                        f"{move.product_id.display_name} is untracked and needs one quantity without a lot."
                    )
                move.quantity = float(rows[0].get("quantity") or 0)
            else:
                if any(not row.get("lot_id") and float(row.get("quantity") or 0) > 0 for row in rows):
                    raise ValidationError(f"Lot allocations are required for {move.product_id.display_name}.")
                if tracking == "serial" and any(
                    float_compare(
                        float(row.get("quantity") or 0),
                        1,
                        precision_rounding=move.product_uom.rounding,
                    ) != 0
                    for row in rows
                    if float(row.get("quantity") or 0) > 0
                ):
                    raise ValidationError("Each serial-number allocation must have quantity 1.")
                move.quantity = 0
                for row in rows:
                    quantity = float(row.get("quantity") or 0)
                    if float_is_zero(quantity, precision_rounding=move.product_uom.rounding):
                        continue
                    lot = self.env["stock.lot"].browse(row["lot_id"]).exists()
                    if not lot or lot.product_id != move.product_id:
                        raise ValidationError(
                            f"A selected lot does not belong to {move.product_id.display_name}."
                        )
                    values = move._prepare_move_line_vals(quantity=quantity)
                    values["lot_id"] = lot.id
                    self.env["stock.move.line"].create(values)
            move.picked = True

    def _move_done_quantity(self, move):
        return self._number_or_none(getattr(move, "quantity", None)) or 0.0

    def _quantity_remaining(self, production):
        produced = self._number_or_none(getattr(production, "qty_produced", None)) or 0.0
        return max(production.product_qty - produced, 0.0)

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

    def _require_quality_access(self, operation):
        self.env["hg.quality.check"].check_access(operation)

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
