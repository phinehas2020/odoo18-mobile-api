import logging
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)


class MobileShopifyFulfillmentService:
    def __init__(self, env):
        self.env = env

    def recent_orders(self, hours=24, limit=50):
        safe_hours = max(min(hours or 24, 168), 1)
        cutoff = fields.Datetime.now() - timedelta(hours=safe_hours)
        domain = [
            ("source", "=", "shopify"),
            ("created_at", ">=", cutoff),
        ]
        safe_limit = max(min(limit or 50, 200), 1)
        _logger.info(
            "mobile_api.shopify_fulfillment.recent_orders.start user_id=%s hours=%s limit=%s",
            self.env.user.id,
            safe_hours,
            safe_limit,
        )
        orders = self.env["shopify.order"].search(
            domain,
            order="created_at desc, id desc",
            limit=safe_limit,
        )
        _logger.info(
            "mobile_api.shopify_fulfillment.recent_orders.success user_id=%s count=%s domain=%s",
            self.env.user.id,
            len(orders),
            domain,
        )
        return [self.order_item(order) for order in orders]

    def order_item(self, order):
        return {
            "id": order.id,
            "shopify_id": self._text_or_none(order.shopify_id) or str(order.id),
            "order_name": self._text_or_none(order.order_name),
            "created_at": order.created_at,
            "customer_name": self._text_or_none(order.customer_name),
            "state": self._text_or_none(order.state),
            "total_items": int(order.total_items or 0),
            "requested_shipping_method": self._text_or_none(
                order.requested_shipping_method
            ),
        }

    def _text_or_none(self, value):
        if isinstance(value, str) and value:
            return value
        return None

