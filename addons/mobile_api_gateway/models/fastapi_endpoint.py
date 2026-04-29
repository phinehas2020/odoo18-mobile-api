from odoo import models

from ..routers import router as gateway_router


class FastapiEndpoint(models.Model):
    _inherit = "fastapi.endpoint"

    def _get_fastapi_routers(self):
        routers = super()._get_fastapi_routers()
        if self.app == "mobile_api":
            routers.append(gateway_router)
        return routers
