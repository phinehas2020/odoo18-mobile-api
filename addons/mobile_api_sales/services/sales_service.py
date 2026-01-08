class MobileSalesService:
    def __init__(self, env):
        self.env = env

    def search_customers(self, search):
        domain = [("customer_rank", ">", 0)]
        if search:
            domain.append(("name", "ilike", search))
        partners = self.env["res.partner"].search(domain, limit=50)
        return [
            {
                "id": partner.id,
                "name": partner.name,
                "email": partner.email,
                "phone": partner.phone,
            }
            for partner in partners
        ]

    def list_orders(self, state=None, updated_since=None):
        domain = []
        if state:
            domain.append(("state", "in", state))
        if updated_since:
            domain.append(("write_date", ">=", updated_since))
        orders = self.env["sale.order"].search(domain, order="write_date desc")
        return [self._order_item(order) for order in orders]

    def get_order(self, order_id):
        order = self.env["sale.order"].browse(order_id)
        if not order.exists():
            return None
        return self._order_detail(order)

    def add_note(self, order_id, note):
        order = self.env["sale.order"].browse(order_id)
        if not order.exists():
            return None
        order.message_post(body=note, subtype_xmlid="mail.mt_note")
        return True

    def _order_item(self, order):
        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_name": order.partner_id.display_name if order.partner_id else None,
            "date_order": order.date_order,
        }

    def _order_detail(self, order):
        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_name": order.partner_id.display_name if order.partner_id else None,
            "date_order": order.date_order,
            "note": order.note,
            "lines": [
                {
                    "id": line.id,
                    "product_name": line.product_id.display_name,
                    "quantity": line.product_uom_qty,
                    "price_subtotal": line.price_subtotal,
                }
                for line in order.order_line
            ],
        }
