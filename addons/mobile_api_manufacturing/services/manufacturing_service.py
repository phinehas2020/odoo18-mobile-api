import logging

from odoo import fields

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
            }
        )
        _logger.info(
            "mobile_api.manufacturing.get_order.success user_id=%s order_id=%s components=%s",
            self.env.user.id,
            order_id,
            len(item["components"]),
        )
        return item

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
            "planned_date": production.date_start,
            "deadline": production.date_deadline,
            "assigned_user_name": self._text_or_none(production.user_id.display_name)
            if production.user_id
            else None,
            "attention_reason": self._attention_reason(production),
        }

    def component_item(self, move):
        return {
            "id": move.id,
            "product_id": move.product_id.id if move.product_id else None,
            "product_name": self._text_or_none(move.product_id.display_name)
            or f"Product {move.product_id.id if move.product_id else move.id}",
            "quantity": move.product_uom_qty,
            "reserved_quantity": getattr(move, "reserved_availability", None),
            "done_quantity": getattr(move, "quantity_done", None),
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

    def _text_or_none(self, value):
        if isinstance(value, str) and value:
            return value
        return None
