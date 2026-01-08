# OpenAPI Publishing

The FastAPI endpoint is mounted at `/api`.

- OpenAPI JSON: `/api/openapi.json`
- Swagger UI: `/api/docs`
- ReDoc: `/api/redoc`

To expose docs externally, enable the FastAPI endpoint and ensure the `/api` route is reachable through your reverse proxy.
