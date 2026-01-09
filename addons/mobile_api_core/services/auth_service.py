import hashlib
import secrets
import uuid
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied


class MobileAuthService:
    def __init__(self, env):
        self.env = env

    def _config_int(self, key, default):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _validator_name(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mobile_api.jwt.validator_name")
            or "mobile_api"
        )

    def _validator(self):
        return (
            self.env["auth.jwt.validator"]
            .sudo()
            ._get_validator_by_name(self._validator_name())
        )

    def _refresh_salt(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mobile_api.refresh_token.salt")
            or ""
        )

    def _device_revoked(self, device_id):
        if not device_id:
            return False
        device = (
            self.env["mobile.device"]
            .sudo()
            .search([("device_id", "=", device_id)], limit=1)
        )
        return bool(device and device.revoked_at)

    def _resolve_company_id(self, user, requested_company_id=None, session_company=None):
        allowed_company_ids = set(user.company_ids.ids)
        if requested_company_id and requested_company_id in allowed_company_ids:
            return requested_company_id
        if session_company and session_company.id in allowed_company_ids:
            return session_company.id
        if user.company_id:
            return user.company_id.id
        return None

    def _hash_refresh_token(self, refresh_token):
        digest = hashlib.sha256()
        digest.update(f"{self._refresh_salt()}{refresh_token}".encode("utf-8"))
        return digest.hexdigest()

    def _access_ttl(self):
        return self._config_int("mobile_api.jwt.access_ttl_seconds", 900)

    def _refresh_ttl(self):
        return self._config_int("mobile_api.jwt.refresh_ttl_seconds", 2592000)

    def _rate_limit_window(self):
        return self._config_int("mobile_api.auth.rate_limit.window_seconds", 900)

    def _rate_limit_max(self):
        return self._config_int("mobile_api.auth.rate_limit.max", 5)

    def check_login_rate_limit(self, login, ip_address):
        window_seconds = self._rate_limit_window()
        max_attempts = self._rate_limit_max()
        if max_attempts <= 0:
            return
        cutoff = fields.Datetime.now() - timedelta(seconds=window_seconds)
        domain = [("success", "=", False), ("attempted_at", ">=", cutoff)]
        if login:
            domain.append(("login", "=", login))
        if ip_address:
            domain.append(("ip_address", "=", ip_address))
        attempts = self.env["mobile.auth.login.attempt"].sudo().search_count(domain)
        if attempts >= max_attempts:
            raise ValueError("rate_limited")

    def record_login_attempt(self, login, ip_address, device_id, success):
        self.env["mobile.auth.login.attempt"].sudo().create(
            {
                "login": login,
                "ip_address": ip_address,
                "device_id": device_id,
                "success": success,
            }
        )

    def authenticate(self, db, login, password):
        try:
            response = (
                self.env["res.users"]
                .sudo()
                .authenticate(
                    db=db,
                    credential={
                        "type": "password",
                        "login": login,
                        "password": password,
                    },
                    user_agent_env=None,
                )
            )
        except AccessDenied:
            return None
        if not response:
            return None
        uid = response.get("uid")
        if not uid:
            return None
        return self.env["res.users"].browse(uid).sudo()

    def _build_access_token(self, user, device_id, company_id=None):
        validator = self._validator()
        access_ttl = self._access_ttl()
        jti = str(uuid.uuid4())
        payload = {
            "uid": user.id,
            "device_id": device_id,
            "jti": jti,
            "allowed_company_ids": user.company_ids.ids,
            "company_id": company_id,
        }
        access_token = validator._encode(
            payload,
            secret=validator.secret_key,
            expire=access_ttl,
        )
        return access_token, jti, access_ttl

    def issue_tokens(self, user, device_id, device_name, company_id=None):
        if self._device_revoked(device_id):
            raise ValueError("device_revoked")
        company_id = self._resolve_company_id(user, requested_company_id=company_id)
        self._upsert_device(user, device_id, device_name)
        access_token, jti, access_ttl = self._build_access_token(
            user, device_id, company_id
        )
        refresh_token = secrets.token_urlsafe(48)
        refresh_hash = self._hash_refresh_token(refresh_token)
        refresh_expires_at = fields.Datetime.now() + timedelta(seconds=self._refresh_ttl())
        self.env["mobile.auth.session"].sudo().create(
            {
                "user_id": user.id,
                "device_id": device_id,
                "device_name": device_name,
                "refresh_token_hash": refresh_hash,
                "refresh_token_expires_at": refresh_expires_at,
                "access_jti": jti,
                "last_seen_at": fields.Datetime.now(),
                "company_id": company_id,
            }
        )
        return access_token, refresh_token, access_ttl, company_id

    def refresh_tokens(self, refresh_token, device_id, company_id=None):
        refresh_hash = self._hash_refresh_token(refresh_token)
        session = (
            self.env["mobile.auth.session"]
            .sudo()
            .search(
                [
                    ("refresh_token_hash", "=", refresh_hash),
                    ("device_id", "=", device_id),
                    ("revoked_at", "=", False),
                ],
                limit=1,
            )
        )
        if not session:
            return None
        if self._device_revoked(device_id):
            return None
        if session.refresh_token_expires_at and session.refresh_token_expires_at < fields.Datetime.now():
            return None
        user = session.user_id
        company_id = self._resolve_company_id(
            user, requested_company_id=company_id, session_company=session.company_id
        )
        self._upsert_device(user, device_id, session.device_name)
        access_token, jti, access_ttl = self._build_access_token(
            user, device_id, company_id
        )
        new_refresh_token = secrets.token_urlsafe(48)
        session.write(
            {
                "refresh_token_hash": self._hash_refresh_token(new_refresh_token),
                "refresh_token_expires_at": fields.Datetime.now()
                + timedelta(seconds=self._refresh_ttl()),
                "access_jti": jti,
                "last_seen_at": fields.Datetime.now(),
                "company_id": company_id,
            }
        )
        return access_token, new_refresh_token, access_ttl, user, company_id

    def revoke_refresh_token(self, refresh_token, device_id):
        refresh_hash = self._hash_refresh_token(refresh_token)
        session = (
            self.env["mobile.auth.session"]
            .sudo()
            .search(
                [
                    ("refresh_token_hash", "=", refresh_hash),
                    ("device_id", "=", device_id),
                    ("revoked_at", "=", False),
                ],
                limit=1,
            )
        )
        if not session:
            return False
        session.write({"revoked_at": fields.Datetime.now()})
        return True

    def revoke_sessions(self, user_id=None, device_id=None):
        domain = [("revoked_at", "=", False)]
        if user_id:
            domain.append(("user_id", "=", user_id))
        if device_id:
            domain.append(("device_id", "=", device_id))
        sessions = self.env["mobile.auth.session"].sudo().search(domain)
        if sessions:
            sessions.write({"revoked_at": fields.Datetime.now()})
        return len(sessions)

    def _upsert_device(self, user, device_id, device_name):
        if not device_id:
            return
        device = (
            self.env["mobile.device"]
            .sudo()
            .search([("device_id", "=", device_id)], limit=1)
        )
        values = {
            "user_id": user.id,
            "device_id": device_id,
            "device_name": device_name,
            "platform": "ios",
            "last_seen_at": fields.Datetime.now(),
        }
        if device:
            device.write(values)
        else:
            self.env["mobile.device"].sudo().create(values)
