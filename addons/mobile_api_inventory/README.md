# Mobile inventory API contracts

All routes below are mounted under `/api/v1` and require the existing JWT-authenticated Odoo environment.

## Receipt line entry

`PATCH /inventory/pickings/{picking_id}/lines/{line_id}` sets a move line's completed quantity. `qty_done` is an absolute value, not an increment, which makes retries safe. The request requires unique `event_id` and `device_id` values and accepts `record_version`, `lot_id`, and `lot_name`. Replaying the same event for the same line returns the current line without writing again; reuse against another line is rejected.

Tracked products require a lot or serial when the completed quantity is positive. Existing lots are checked against the product, company, and operation-type policy. A new `lot_name` is accepted only for incoming operations whose Odoo picking type permits lot creation. Serial move lines accept only zero or one unit.

The response contains `status`, the updated `line` (including `move_id`, `lot_id`, and `lot_name`), the new `record_version`, and `warnings`.

Picking detail also includes demand-level `moves`, even when Odoo has not created any move lines yet. `POST /inventory/pickings/{picking_id}/lines` accepts the same quantity and lot fields plus `move_id` and creates an explicit move line. Serial receipts use one line with quantity one per serial number; clients repeat the POST with a new event ID and current record version for each serial.

## Safe completion and backorders

`POST /inventory/pickings/{picking_id}/validate` accepts `backorder_policy` with `ask` (default), `create`, or `cancel`.

When Odoo 18 returns a `stock.backorder.confirmation` action, `ask` returns `status: needs_backorder` and `backorder_required: true`; it never reports the transfer as completed. The client then submits a new event ID and current record version with either `create` or `cancel`. Those choices run Odoo's `stock.backorder.confirmation.process()` or `process_cancel_backorder()` respectively. Success is returned only after the original picking is in `done` state. A created backorder is exposed as `backorder_picking_id`.

Record versions include the picking, demand moves, and move-line values. Receipt lookups happen before version checks so a network retry of an already processed event remains idempotent.

Scan responses also return `record_version`; clients must replace their prior token before the next picking mutation.

## Stock operations

`GET /inventory/stock` searches existing nonzero quant rows in the current company's internal, non-scrap locations. It returns exact quant identities and `can_adjust`/`can_scrap` flags. The mutation routes also enforce Odoo's Inventory Manager group on the server.

Counts use `POST /inventory/adjustments/review` followed by `POST /inventory/adjustments/apply`. Scrap uses the equivalent `/inventory/scraps/review` and `/inventory/scraps/apply` routes. Apply requests require the reviewed flag, the review's record version, and an idempotency event ID. Counts call `stock.quant.action_apply_inventory`; scraps call `stock.scrap.action_validate`. If Odoo returns another warning wizard, the API stops without claiming success.

Completed-transfer returns use `POST /inventory/pickings/{id}/returns/review` to calculate currently returnable move quantities, then `/returns/apply` with selected `{move_id, quantity}` rows. Apply recreates and runs Odoo's `stock.return.picking` wizard and returns the new picking identity.
