from odoo import fields, models

from starlette.middleware import Middleware

from odoo.addons.fastapi_auth_jwt import dependencies as auth_jwt_deps

from ..routers import router as mobile_api_router
from ..services.log_middleware import MobileApiLogMiddleware


class FastapiEndpoint(models.Model):
    _inherit = "fastapi.endpoint"

    app = fields.Selection(
        selection_add=[("mobile_api", "Mobile API")],
        ondelete={"mobile_api": "cascade"},
    )
    mobile_api_validator_name = fields.Char(
        string="Mobile API JWT Validator",
        default="mobile_api",
    )

    def _fastapi_app_fields(self):
        fields_to_watch = super()._fastapi_app_fields()
        return list(fields_to_watch) + ["mobile_api_validator_name"]

    def _get_fastapi_routers(self):
        routers = super()._get_fastapi_routers()
        if self.app == "mobile_api":
            routers.append(mobile_api_router)
        return routers

    def _get_fastapi_app_middlewares(self):
        middlewares = super()._get_fastapi_app_middlewares()
        if self.app == "mobile_api":
            middlewares.append(Middleware(MobileApiLogMiddleware))
        return middlewares

    def _get_app_dependencies_overrides(self):
        overrides = super()._get_app_dependencies_overrides()
        if self.app == "mobile_api":
            self.ensure_one()
            validator_name = self.mobile_api_validator_name
            overrides[
                auth_jwt_deps.auth_jwt_default_validator_name
            ] = lambda validator_name=validator_name: validator_name
        return overrides
