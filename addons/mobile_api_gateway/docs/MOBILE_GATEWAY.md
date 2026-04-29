# Mobile API Gateway

`mobile_api_gateway` is the overarching native-app API layer for Odoo. It is not tied to Smart Label Printer, Inventory, or Sales. Those workflows become specializations on top of the gateway.

## What It Provides

- `GET /api/v1/gateway/manifest`
  - Returns the signed-in user's mobile-visible models and workflow routes.
- `GET /api/v1/gateway/models`
  - Lists Odoo models available to the mobile user.
- `GET /api/v1/gateway/models/{model}`
  - Returns field metadata for a model.
- `GET /api/v1/gateway/models/{model}/records`
  - Lists records with pagination, search, field selection, and optional JSON domain.
- `GET /api/v1/gateway/models/{model}/records/{id}`
  - Returns one record.
- `POST /api/v1/gateway/models/{model}/records`
  - Creates records only for models explicitly enabled in `mobile_api_gateway.create_models`.
- `PATCH /api/v1/gateway/models/{model}/records/{id}`
  - Updates records only for models explicitly enabled in `mobile_api_gateway.write_models`.
- `POST /api/v1/gateway/models/{model}/records/{id}/methods/{method}`
  - Calls model methods only when explicitly enabled in `mobile_api_gateway.allowed_methods`.

## How It Grows With Odoo

The gateway discovers readable models from:

- installed Odoo model registry,
- menu actions the user can access,
- a built-in mobile-safe allowlist,
- `mobile_api_gateway.extra_models` config parameter.

When a new Odoo app is installed and exposes normal models/menu actions, the gateway can show it without a new iOS release. The iOS app can start with metadata-driven list/detail screens, then graduate important flows into custom native screens.

## Guardrails

The gateway is not a raw ORM tunnel.

- Odoo access rights and record rules still apply.
- Technical models like `ir.*`, `base.*`, `res.users`, `ir.config_parameter`, and attachments are blocked by default.
- Binary fields are not exposed.
- Create/write are disabled by default.
- Methods/actions are disabled by default unless allowed by exact `model.method` name.

## Useful Config Parameters

Comma-separated values:

- `mobile_api_gateway.extra_models`
- `mobile_api_gateway.blocked_models`
- `mobile_api_gateway.create_models`
- `mobile_api_gateway.write_models`
- `mobile_api_gateway.allowed_methods`

Example:

```text
mobile_api_gateway.extra_models = smart.label.job,smart.label.device,smart.label.profile
mobile_api_gateway.create_models = smart.label.job
mobile_api_gateway.write_models = smart.label.job
mobile_api_gateway.allowed_methods = stock.picking.button_validate,sale.order.action_confirm,smart.label.job.action_cancel
```

## Smart Labels On The Gateway

Smart Labels no longer needs to be the whole API idea. It can use generic gateway routes for discovery and status:

- `/gateway/models/smart.label.device/records`
- `/gateway/models/smart.label.job/records`
- `/gateway/models/product.product/records?search=einkorn`

For queueing a label job, keep a workflow adapter such as `/smart-label/jobs` because it runs business logic from `smart.label.print.wizard` and should not be reduced to raw record creation.
