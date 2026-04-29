from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GatewayLink(BaseModel):
    rel: str
    href: str
    method: str = "GET"


class GatewayWorkflow(BaseModel):
    key: str
    label: str
    model: Optional[str] = None
    native_route: Optional[str] = None
    links: List[GatewayLink] = []


class GatewayModelSummary(BaseModel):
    model: str
    label: str
    module: Optional[str] = None
    read: bool = True
    create: bool = False
    write: bool = False
    actions: List[str] = []
    links: List[GatewayLink] = []


class GatewayField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False
    readonly: bool = False
    relation: Optional[str] = None
    selection: Optional[List[List[Any]]] = None
    searchable: bool = False


class GatewayManifest(BaseModel):
    version: str = "1"
    user_id: int
    company_id: Optional[int] = None
    models: List[GatewayModelSummary]
    workflows: List[GatewayWorkflow]
    links: List[GatewayLink]


class GatewayModelList(BaseModel):
    models: List[GatewayModelSummary]


class GatewayModelDetail(GatewayModelSummary):
    fields: List[GatewayField] = []
    default_list_fields: List[str] = []
    default_detail_fields: List[str] = []


class GatewayRecordList(BaseModel):
    model: str
    total: int
    limit: int
    offset: int
    records: List[Dict[str, Any]]
    links: List[GatewayLink] = []


class GatewayRecordDetail(BaseModel):
    model: str
    id: int
    record: Dict[str, Any]
    links: List[GatewayLink] = []


class GatewayWriteRequest(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class GatewayMethodRequest(BaseModel):
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class GatewayMethodResponse(BaseModel):
    model: str
    id: int
    method: str
    result: Any = None
