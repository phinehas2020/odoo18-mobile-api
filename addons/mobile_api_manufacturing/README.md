# Mobile API Manufacturing

Authenticated operators using the manufacturing order, completion, work order,
or quality endpoints must have both **Manufacturing / User**
(`mrp.group_mrp_user`) and **Quality Control / Quality Operator**
(`hg_quality.group_quality_operator`) access. The API preserves Odoo ACLs and
record rules; it does not elevate a caller who lacks quality access, and returns
HTTP 403 for those protected workflows.

Settings administrators keep the cross-user manufacturing work-list view.
Regular users only receive manufacturing orders assigned to their Odoo user.
