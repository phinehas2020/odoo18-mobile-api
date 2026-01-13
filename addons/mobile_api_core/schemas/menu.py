from typing import List, Optional

from pydantic import BaseModel


class MenuItem(BaseModel):
    key: str
    label: str
    enabled: bool = True
    deep_link: Optional[str] = None
    icon: Optional[str] = None
    web_url: Optional[str] = None
    native: bool = False  # True if native mobile view exists


class MenuResponse(BaseModel):
    items: List[MenuItem]
