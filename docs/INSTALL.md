# Mobile API Install & Configuration (Odoo 18)

## Dependencies
Install OCA addons (18.0 branches):
- OCA/rest-framework: `fastapi`, `fastapi_auth_jwt`, `pydantic`, `rest_log`
- OCA/server-auth: `auth_jwt`
- OCA/queue: `queue_job`

Python dependencies are listed in `requirements.txt` at the repo root.

## Addons Path
Add this repo to your Odoo addons path:

```
--addons-path=/path/to/odoo/addons,/path/to/odoo18-mobile-api/addons
```

## Install Modules
Install in this order:
1. `mobile_api_core`
2. `mobile_api_sync`
3. `mobile_api_inventory`
4. `mobile_api_sales`
5. `mobile_api_push`
6. `mobile_api_admin`

## FastAPI Endpoint
The `mobile_api_core` module creates a FastAPI endpoint record:
- Root Path: `/api`
- App: `mobile_api`
- OpenAPI: `/api/openapi.json`
- Docs: `/api/docs`

## JWT Configuration
The post-init hook generates:
- `mobile_api.jwt.secret`
- `mobile_api.refresh_token.salt`
- `mobile_api.jwt.issuer` (default: `odoo`)
- `mobile_api.jwt.audience` (default: `mobile`)

JWT validator record is created as `mobile_api`.

## Rest Log
Rest logs are stored in `rest.log` (menu: Mobile API → API Logs).
Enable logging for all mobile routes by setting the system parameter:

```
rest.log.active = mobile_api
```

## Queue Job
Channels are created:
- `mobile.push.high`
- `mobile.sync.normal`
- `mobile.maintenance.low`

Ensure a queue job worker is running.

## APNS
Set system parameters:
- `mobile_api.apns.team_id`
- `mobile_api.apns.key_id`
- `mobile_api.apns.bundle_id`
- `mobile_api.apns.private_key` (contents of the .p8 key)
- `mobile_api.apns.use_sandbox` (true/false)

## Default Settings
- `mobile_api.jwt.access_ttl_seconds`
- `mobile_api.jwt.refresh_ttl_seconds`
- `mobile_api.auth.rate_limit.max`
- `mobile_api.auth.rate_limit.window_seconds`
- `mobile_api.barcode.scan_mode`
- `mobile_api.barcode.keyboard_wedge`
- `mobile_api.offline.max_pending`
- `mobile_api.offline.auto_sync`
