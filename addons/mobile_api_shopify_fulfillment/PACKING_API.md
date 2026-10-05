# Packing API

All routes are under `/api/v1/shopify/packing`. They require the existing mobile
Bearer JWT, an active employee account, a registered non-revoked device owned by
that account, and an explicit signed company that the user can still access.
After token/device verification the bridge supplies a private process-local
marker that serialized Odoo RPC context cannot forge; it is never returned in API
payloads. Business record operations run as that user in that one company. The fulfillment
add-on also verifies its packing permissions and warehouse scope.

GET routes require `X-Device-ID` matching the JWT's `device_id`. POST/PATCH bodies
require that same `device_id`. A supplied device header must also match. Invalid
requests are rejected before business operations. Responses are `Cache-Control:
no-store`; this workflow does not use the generic sync dispatcher or offline
outbox.

| Method | Path | Body | Result |
| --- | --- | --- | --- |
| GET | `/capabilities` | None | `enabled`, `business_enabled`, `can_pack`, `can_supervise`, `requires_online`, `workflow_version` |
| POST | `/resolve` | `device_id`, `barcode` and optional `symbology`, or `candidates: [{barcode, symbology}]` | Bare `PackingDetail` plus selected `resolved_barcode` and optional `resolved_symbology` |
| GET | `/{shipment_id}` | None | Fresh bare `PackingDetail` |
| POST | `/{shipment_id}/claim` | `device_id`, `version`, `event_id`, optional supervisor `user_id` | Bare `PackingDetail` |
| PATCH | `/{shipment_id}/items/{line_id}` | `device_id`, `version`, `event_id`, absolute `quantity` | Bare `PackingDetail` |
| POST | `/{shipment_id}/complete` | `device_id`, `version`, `event_id`, `barcode`, optional `symbology` | Bare `PackingDetail` |

`event_id` is a UUID and `version` is a positive integer. Confirmed quantities
must be finite, non-negative whole item units. Domain checks enforce allocation limits,
ownership, same-label confirmation, eligibility, and version conflicts. Domain
receipts bind each event to its actor/device/action/record/payload.

At most eight scan candidates are allowed. Repeated identical candidates are
deduplicated. Unknown/unsupported barcode candidates can be ignored only when
one unique box resolves. Multiple matching boxes return `409 ambiguous_label`.
Known label holds are retained. Resolve never claims a box or completes stock,
accounting, Shopify fulfillment, purchase, or printing.

The full response fields are defined in `schemas/packing.py`. Local physical
`packing_state`, operational `operational_state`, and outbound `sync_state` are
separate; a response must never infer delivery success from a packed box alone.
API/domain errors are `{ "detail": { "code": "...", "message": "..." } }` with
the corresponding HTTP status. Pydantic request validation uses FastAPI's usual
422 validation shape.

Phone mutations require both `fulfillment.packing_enabled` and
`fulfillment.packing_native_enabled` to be true. Native menu visibility and
capabilities `enabled` follow the native flag; `business_enabled` follows the
business flag. Thus native `true` and business `false` expose a read-only preview
for actual label verification before the coordinated business cutover. The app
must gate every mutation on both flags and authoritative allowed actions.
Disabling the native flag stops phone writes while retaining the guarded Odoo
operation and immutable order completion policy. It cannot restore the old
print-triggered fulfillment path. Authorized read-only lookup remains available
for review while native writes are disabled.

`tests/test_packing_api.py` uses disposable database records and mocks the
canonical resolver/finalizer; it performs no provider purchases, printing,
inventory moves, or financial postings.
