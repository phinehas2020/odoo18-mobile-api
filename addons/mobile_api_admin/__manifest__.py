{
    "name": "Mobile API Admin",
    "summary": "Admin menus for Mobile API monitoring",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": [
        "mobile_api_core",
        "mobile_api_sync",
        "mobile_api_push",
        "rest_log",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/mobile_api_admin_views.xml",
        "views/mobile_api_admin_menus.xml",
    ],
    "installable": True,
    "application": False,
}
