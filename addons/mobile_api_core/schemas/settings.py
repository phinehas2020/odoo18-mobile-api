from typing import Dict

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    barcode: Dict[str, str]
    offline: Dict[str, str]
