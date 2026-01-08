from typing import List, Optional

from pydantic import BaseModel


class MenuItem(BaseModel):
    key: str
    label: str
    enabled: bool = True
    deep_link: Optional[str] = None


class MenuResponse(BaseModel):
    items: List[MenuItem]
