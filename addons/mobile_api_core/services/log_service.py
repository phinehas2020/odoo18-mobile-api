import json

class MobileApiLogService:
    def __init__(self, env):
        self.env = env

    def _logging_active(self):
        return self.env["rest.log"].logging_active()

    def _sanitize_headers(self, headers):
        redacted = {}
        for key, value in headers.items():
            if key.lower() in {"authorization", "cookie", "api-key"}:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = value
        return redacted

    def _sanitize_params(self, params):
        params = dict(params)
        if "password" in params:
            params["password"] = "<redacted>"
        body = params.get("body")
        if isinstance(body, dict) and "password" in body:
            body = dict(body)
            body["password"] = "<redacted>"
            params["body"] = body
        return params

    def _json_dump(self, value):
        return json.dumps(value, indent=2, sort_keys=True, default=str)

    def log_request(
        self,
        request,
        response=None,
        error=None,
        exception_name=None,
        exception_message=None,
        duration_ms=None,
        user_id=None,
        device_id=None,
    ):
        if not self._logging_active():
            return None

        params = {
            "query": dict(request.query_params),
            "user_id": user_id,
            "device_id": device_id,
        }
        if hasattr(request.state, "mobile_api_body") and request.state.mobile_api_body:
            params["body"] = request.state.mobile_api_body
        params = self._sanitize_params(params)

        headers = self._sanitize_headers(dict(request.headers))

        result = None
        state = "failed" if error else "success"
        if response is not None:
            result = {
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        values = {
            "collection": "mobile_api",
            "collection_id": None,
            "request_url": str(request.url),
            "request_method": request.method,
            "params": self._json_dump(params),
            "headers": self._json_dump(headers),
            "result": self._json_dump(result) if result is not None else None,
            "error": error,
            "exception_name": exception_name,
            "exception_message": exception_message,
            "state": state,
        }

        return self.env["rest.log"].sudo().create(values)
