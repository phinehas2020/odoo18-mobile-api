from typing import List, Optional

from pydantic import BaseModel


class BarcodeAction(BaseModel):
    action: str
    label: Optional[str] = None


class BarcodeResolveResponse(BaseModel):
    match_type: str
    id: int
    name: str
    actions: List[BarcodeAction] = []
