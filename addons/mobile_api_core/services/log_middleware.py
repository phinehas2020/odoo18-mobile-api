import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from odoo.addons.fastapi.context import odoo_env_ctx

from .log_service import MobileApiLogService


class MobileApiLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.monotonic()
        body = await request.body()
        request._body = body
        try:
            if body:
                try:
                    request.state.mobile_api_body = json.loads(body)
                except json.JSONDecodeError:
                    request.state.mobile_api_body = body.decode("utf-8", errors="ignore")
            else:
                request.state.mobile_api_body = None
        except Exception:
            request.state.mobile_api_body = None

        env = None
        try:
            env = odoo_env_ctx.get()
        except LookupError:
            env = None

        if env:
            log_service = MobileApiLogService(env)
        else:
            log_service = None
        user_id = None
        device_id = None
        if env:
            user_id, device_id = self._try_get_token_context(env, request)

        try:
            response = await call_next(request)
        except Exception as exc:
            if log_service:
                log_service.log_request(
                    request,
                    response=None,
                    error=str(exc),
                    exception_name=exc.__class__.__name__,
                    exception_message=str(exc),
                    duration_ms=self._duration_ms(start_time),
                    user_id=user_id,
                    device_id=device_id,
                )
            raise

        log_entry = None
        if log_service:
            log_entry = log_service.log_request(
                request,
                response=response,
                duration_ms=self._duration_ms(start_time),
                user_id=user_id,
                device_id=device_id,
            )

        if log_entry and env:
            log_url = self._log_url(env, log_entry.id)
            response.headers["X-Rest-Log-Id"] = str(log_entry.id)
            response.headers["X-Rest-Log-Url"] = log_url
            response = self._inject_log_url(response, log_url)

        return response

    def _duration_ms(self, start_time):
        return int((time.monotonic() - start_time) * 1000)

    def _try_get_token_context(self, env, request):
        auth_header = request.headers.get("authorization") or request.headers.get(
            "Authorization"
        )
        if not auth_header or not auth_header.startswith("Bearer "):
            return None, None
        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None, None
        try:
            validator_name = (
                env["ir.config_parameter"]
                .sudo()
                .get_param("mobile_api.jwt.validator_name")
                or "mobile_api"
            )
            validator = (
                env["auth.jwt.validator"].sudo()._get_validator_by_name(validator_name)
            )
            payload = validator._decode(token)
            return payload.get("uid"), payload.get("device_id")
        except Exception:
            return None, None

    def _log_url(self, env, log_id):
        base_url = env["ir.config_parameter"].sudo().get_param("web.base.url")
        action_id = env.ref("rest_log.action_rest_log").id
        return f"{base_url}/web#action={action_id}&model=rest.log&id={log_id}"

    def _inject_log_url(self, response, log_url):
        if response.media_type != "application/json":
            return response
        if not hasattr(response, "body") or response.body is None:
            return response
        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError:
            return response
        if not isinstance(payload, dict):
            return response
        if "log_entry_url" not in payload:
            payload["log_entry_url"] = log_url
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return JSONResponse(
                content=payload,
                status_code=response.status_code,
                headers=headers,
            )
        return response
