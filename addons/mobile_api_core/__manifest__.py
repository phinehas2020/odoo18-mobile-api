{
    "name": "Mobile API Core",
    "summary": "FastAPI foundation, JWT auth, and core endpoints for mobile apps",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": [
        "base",
        "fastapi",
        "fastapi_auth_jwt",
        "pydantic",
        "rest_log",
        "auth_jwt",
        "queue_job",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/mobile_api_core_data.xml",
        "data/queue_job_channels.xml",
    ],
    "post_init_hook": "mobile_api_post_init",
    "installable": True,
    "application": False,
}
