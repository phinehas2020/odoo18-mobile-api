from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ShopifyRecentOrderItem(BaseModel):
    id: int
    shopify_id: str
    order_name: Optional[str] = None
    created_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    state: Optional[str] = None
    total_items: int = 0
    requested_shipping_method: Optional[str] = None

