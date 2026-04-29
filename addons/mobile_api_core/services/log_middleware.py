import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from odoo.addons.fastapi.context import odoo_env_ctx

from .log_service import MobileApiLogService

_logger = logging.getLogger(__name__)


class MobileApiLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.endswith(("/docs", "/openapi.json", "/redoc")):
            return await call_next(request)

        start_time = time.monotonic()
        request_id = (
            request.headers.get("x-mobile-client-request-id")
            or request.headers.get("X-Mobile-Client-Request-Id")
            or str(uuid.uuid4())
        )
        request.state.mobile_api_request_id = request_id
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

        _logger.info(
            "mobile_api.request.start request_id=%s method=%s path=%s query=%s user_id=%s device_id=%s",
            request_id,
            request.method,
            request.url.path,
            dict(request.query_params),
            user_id,
            device_id,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = self._duration_ms(start_time)
            _logger.exception(
                "mobile_api.request.exception request_id=%s method=%s path=%s duration_ms=%s user_id=%s device_id=%s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                user_id,
                device_id,
            )
            if log_service:
                log_service.log_request(
                    request,
                    response=None,
                    error=str(exc),
                    exception_name=exc.__class__.__name__,
                    exception_message=str(exc),
                    duration_ms=duration_ms,
                    user_id=user_id,
                    device_id=device_id,
                )
            raise

        log_entry = None
        duration_ms = self._duration_ms(start_time)
        if log_service:
            log_entry = log_service.log_request(
                request,
                response=response,
                duration_ms=duration_ms,
                user_id=user_id,
                device_id=device_id,
            )

        if log_entry and env:
            log_url = self._log_url(env, log_entry.id)
            response.headers["X-Rest-Log-Id"] = str(log_entry.id)
            response.headers["X-Rest-Log-Url"] = log_url
            response = self._inject_log_url(response, log_url)
        response.headers["X-Mobile-Request-Id"] = request_id

        _logger.info(
            "mobile_api.request.end request_id=%s method=%s path=%s status=%s duration_ms=%s rest_log_id=%s user_id=%s device_id=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            log_entry.id if log_entry else None,
            user_id,
            device_id,
        )

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
