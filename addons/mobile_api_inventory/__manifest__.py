{
    "name": "Mobile API Inventory",
    "summary": "Inventory endpoints for mobile app",
    "version": "18.0.1.0.0",
    "category": "Inventory",
    "license": "LGPL-3",
    "depends": [
        "mobile_api_sync",
        "stock",
        "stock_barcode",
        "fastapi",
        "pydantic",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
