import time

import httpx
import jwt


class ApnsClient:
    def __init__(self, env):
        config = env["ir.config_parameter"].sudo()
        self.team_id = config.get_param("mobile_api.apns.team_id")
        self.key_id = config.get_param("mobile_api.apns.key_id")
        self.bundle_id = config.get_param("mobile_api.apns.bundle_id")
        self.private_key = config.get_param("mobile_api.apns.private_key")
        self.use_sandbox = config.get_param("mobile_api.apns.use_sandbox", "false")

    def _endpoint(self):
        if (self.use_sandbox or "").lower() == "true":
            return "https://api.sandbox.push.apple.com"
        return "https://api.push.apple.com"

    def _jwt_token(self):
        now = int(time.time())
        payload = {"iss": self.team_id, "iat": now}
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )

    def send(self, device_token, payload, topic=None):
        if not device_token:
            return {"status": "failed", "message": "Missing device token"}
        if not all([self.team_id, self.key_id, self.bundle_id, self.private_key]):
            return {"status": "failed", "message": "APNS config incomplete"}

        token = self._jwt_token()
        url = f"{self._endpoint()}/3/device/{device_token}"
        headers = {
            "authorization": f"bearer {token}",
            "apns-topic": topic or self.bundle_id,
            "apns-push-type": "alert",
        }
        with httpx.Client(http2=True, timeout=10.0) as client:
            response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 200 and response.status_code < 300:
            return {"status": "success"}
        return {
            "status": "failed",
            "message": response.text or "APNS error",
            "status_code": response.status_code,
        }
