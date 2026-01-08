# Adding a New Mobile Module

## Server (Odoo)
1. Create a new addon `mobile_api_<module>`.
2. Add FastAPI routers in `routers/` and schemas in `schemas/`.
3. Extend `fastapi.endpoint` in `models/fastapi_endpoint.py` to include your router when `app == "mobile_api"`.
4. Use stable workflow endpoints under `/api/v1/...` (do not expose raw ORM endpoints).
5. Add change tracking by inheriting `mobile.change.log.mixin` where relevant.
6. Implement outbox handlers by extending `mobile.sync.service` with `_handle_<action>()`.
7. Add tests in `tests/` using `FastAPITransactionCase`.

## iOS
1. Add Codable models in `Core/Models` for the new endpoints.
2. Create an MVVM module in `Features/<Module>`.
3. Register any offline actions through `OutboxStore` and define action types to match server handlers.
4. Add module tile in `/api/v1/menu` response and handle deep links in `DeepLinkParser`.

## Auth Company Selection
- `company_id` is optional on `/api/v1/auth/login` and `/api/v1/auth/refresh` to set the active company in JWT.
- Reject company ids outside `allowed_company_ids`.

## Versioning
All endpoints must remain under `/api/v1`. Breaking changes require adding a new `/api/v2` namespace.
