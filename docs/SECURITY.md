# Security Operations

## Token Revoke
- Revoke a device/session: POST `/api/v1/auth/revoke` with `{ "device_id": "..." }`.
- Revoke all user sessions: POST `/api/v1/auth/revoke` with `{ "user_id": 123 }`.

## Device Wipe
- Mark a device revoked by setting `revoked_at` on `mobile.device`.
- Mobile app will force logout on next refresh when device is revoked.

## APNS Key Rotation
1. Generate new APNS key in Apple Developer Portal.
2. Update system parameters:
   - `mobile_api.apns.key_id`
   - `mobile_api.apns.private_key`
3. Restart workers to reload configuration.

## JWT Secret Rotation
1. Update `mobile_api.jwt.secret` and `mobile_api.refresh_token.salt`.
2. Revoke existing sessions (auth revoke) to force re-login.
