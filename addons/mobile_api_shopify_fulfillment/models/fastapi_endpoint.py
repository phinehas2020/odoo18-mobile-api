from odoo import models

from ..routers import router as shopify_fulfillment_router


class FastapiEndpoint(models.Model):
    _inherit = "fastapi.endpoint"

    def _get_fastapi_routers(self):
        routers = super()._get_fastapi_routers()
        if self.app == "mobile_api":
            routers.append(shopify_fulfillment_router)
        return routers

