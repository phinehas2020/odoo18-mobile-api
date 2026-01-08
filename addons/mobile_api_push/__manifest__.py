{
    "name": "Mobile API Push",
    "summary": "APNS push notifications for mobile app",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": [
        "mobile_api_core",
        "queue_job",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mobile_api_push_data.xml",
    ],
    "external_dependencies": {
        "python": ["httpx"],
    },
    "installable": True,
    "application": False,
}
