{
    "name": "Mobile API Sync",
    "summary": "Offline sync foundation for Mobile API",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": [
        "mobile_api_core",
        "fastapi",
        "pydantic",
        "queue_job",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mobile_api_sync_data.xml",
    ],
    "installable": True,
    "application": False,
}
