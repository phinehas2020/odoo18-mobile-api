# Smart Label Mobile Workflows

The Smart Label native API is mounted under `/api/v1/smart-label` and uses the shared JWT dependency `auth_jwt_authenticated_odoo_env`. Generic lists and detail screens can use `mobile_api_gateway`; these workflow endpoints exist because they call Odoo wizard and object-button business logic.

## Permission Behavior

- All endpoints run as the authenticated Odoo user from the JWT.
- Odoo ACLs and record rules apply through the normal `env`; the service does not use `sudo`.
- Manufacturing-order creation/opening requires `mrp.group_mrp_user`, matching the web UI section/button.
- Device token rotation requires normal write access on `smart.label.device`.

## Error Mapping

- Missing or record-rule-hidden workflow records: `404`.
- `AccessError`: `403`.
- `UserError`: `400`.
- `ValidationError` or Pydantic schema errors: `422`.
- Unexpected exceptions are logged with `mobile_api.smart_label.<workflow>.route.unexpected_error` and returned as `500`.

## Queue Job

`POST /api/v1/smart-label/jobs`

Calls `smart.label.print.wizard.action_queue_job`, including barcode save, profile creation, label snapshotting, optional device assignment, and optional manufacturing-order creation.

Request schema:

```json
{
  "product_id": 123,
  "device_id": 7,
  "barcode": "012345678905",
  "quantity": 2,
  "label_type": "both",
  "update_inventory": true,
  "create_manufacturing_order": false,
  "manufacturing_user_id": null
}
```

Success example:

```json
{
  "job": {
    "id": 42,
    "name": "JOB-00042",
    "state": "pending",
    "product_id": 123,
    "product_name": "Einkorn Flour",
    "quantity": 2,
    "label_type": "both",
    "device_id": 7,
    "device_name": "Kitchen Printer",
    "result_message": null,
    "manufacturing_order_id": null,
    "manufacturing_order_name": null
  }
}
```

Failure example:

```json
{
  "detail": "Enter a barcode on the wizard or set the Odoo product barcode before printing a back label."
}
```

Log messages:

- `mobile_api.smart_label.queue.route.start`
- `mobile_api.smart_label.queue_job.start`
- `mobile_api.smart_label.queue_job.success`
- `mobile_api.smart_label.queue.route.success`
- `mobile_api.smart_label.queue.route.user_error`
- `mobile_api.smart_label.queue.route.access_error`
- `mobile_api.smart_label.queue.route.not_found`

Curl verification:

```bash
curl -sS "$BASE_URL/api/v1/smart-label/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"product_id":123,"device_id":7,"barcode":"012345678905","quantity":2,"label_type":"both","update_inventory":true}'
```

## Cancel Job

`POST /api/v1/smart-label/jobs/{job_id}/cancel`

Calls `smart.label.job.action_cancel`. The endpoint accepts pending, claimed, or printing jobs, matching the web form button visibility.

Request schema:

```json
{
  "client_action_id": "ios-action-001"
}
```

Success example:

```json
{
  "status": "success",
  "job": {
    "id": 42,
    "name": "JOB-00042",
    "state": "cancelled",
    "product_name": "Einkorn Flour",
    "quantity": 2,
    "label_type": "both"
  }
}
```

Failure example:

```json
{
  "detail": "Job JOB-00042 cannot be cancelled from state done."
}
```

Log messages:

- `mobile_api.smart_label.cancel.route.start`
- `mobile_api.smart_label.cancel_job.start`
- `mobile_api.smart_label.cancel_job.success`
- `mobile_api.smart_label.cancel.route.success`
- `mobile_api.smart_label.cancel.route.user_error`

Curl verification:

```bash
curl -sS "$BASE_URL/api/v1/smart-label/jobs/42/cancel" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_action_id":"ios-action-001"}'
```

## Reset Job

`POST /api/v1/smart-label/jobs/{job_id}/reset`

Calls `smart.label.job.action_reset_to_pending`. The endpoint accepts failed, cancelled, or done jobs, matching the web form button visibility.

Request schema:

```json
{
  "client_action_id": "ios-action-002"
}
```

Success example:

```json
{
  "status": "success",
  "job": {
    "id": 42,
    "name": "JOB-00042",
    "state": "pending",
    "product_name": "Einkorn Flour",
    "quantity": 2,
    "label_type": "both"
  }
}
```

Failure example:

```json
{
  "detail": "Job JOB-00042 cannot be reset from state printing."
}
```

Log messages:

- `mobile_api.smart_label.reset.route.start`
- `mobile_api.smart_label.reset_job.start`
- `mobile_api.smart_label.reset_job.success`
- `mobile_api.smart_label.reset.route.success`
- `mobile_api.smart_label.reset.route.user_error`

Curl verification:

```bash
curl -sS "$BASE_URL/api/v1/smart-label/jobs/42/reset" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_action_id":"ios-action-002"}'
```

## Open Manufacturing Order

`POST /api/v1/smart-label/jobs/{job_id}/open-manufacturing-order`

Calls `smart.label.job.action_open_manufacturing_order` and returns a native target plus gateway record link. It never returns a browser URL.

Request schema:

```json
{
  "client_action_id": "ios-action-003"
}
```

Success example:

```json
{
  "status": "success",
  "manufacturing_order": {
    "id": 55,
    "name": "WH/MO/00055",
    "state": "draft",
    "product_id": 123,
    "product_name": "Einkorn Flour",
    "quantity": 2.0,
    "assigned_user_id": 9,
    "assigned_user_name": "Mill Staff"
  },
  "target": {
    "model": "mrp.production",
    "res_id": 55,
    "native_route": "app://manufacturing/production/55",
    "links": [
      {
        "rel": "gateway_record",
        "href": "/api/v1/gateway/models/mrp.production/records/55",
        "method": "GET"
      }
    ]
  }
}
```

Failure example:

```json
{
  "detail": "Job JOB-00042 does not have a manufacturing order."
}
```

Log messages:

- `mobile_api.smart_label.open_manufacturing_order.route.start`
- `mobile_api.smart_label.open_manufacturing_order.start`
- `mobile_api.smart_label.open_manufacturing_order.success`
- `mobile_api.smart_label.open_manufacturing_order.route.success`
- `mobile_api.smart_label.open_manufacturing_order.route.access_error`
- `mobile_api.smart_label.open_manufacturing_order.route.not_found`

Curl verification:

```bash
curl -sS "$BASE_URL/api/v1/smart-label/jobs/42/open-manufacturing-order" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_action_id":"ios-action-003"}'
```

## Rotate Device Token

`POST /api/v1/smart-label/devices/{device_id}/rotate-token`

Calls `smart.label.device.action_rotate_token` and returns the new agent token for device provisioning.

Request schema:

```json
{
  "client_action_id": "ios-action-004"
}
```

Success example:

```json
{
  "status": "success",
  "device": {
    "id": 7,
    "name": "Kitchen Printer",
    "state": "online",
    "stock_location_name": "WH/Stock",
    "inventory_operation": "increase",
    "active": true
  },
  "agent_token": "new-token-value"
}
```

Failure example:

```json
{
  "detail": "Smart label device 999 was not found."
}
```

Log messages:

- `mobile_api.smart_label.rotate_token.route.start`
- `mobile_api.smart_label.rotate_device_token.start`
- `mobile_api.smart_label.rotate_device_token.success`
- `mobile_api.smart_label.rotate_token.route.success`
- `mobile_api.smart_label.rotate_token.route.access_error`
- `mobile_api.smart_label.rotate_token.route.not_found`

Curl verification:

```bash
curl -sS "$BASE_URL/api/v1/smart-label/devices/7/rotate-token" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_action_id":"ios-action-004"}'
```
