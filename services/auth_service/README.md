# auth_service

## Purpose
Handles FYERS authentication lifecycle, session bootstrap, validation, and auth API endpoints.

## Status
Scaffolded with session bootstrap, validation stub, and API endpoints.

## Entry point
Bootstrap mode:
`python3 -m services.auth_service.app.main`

API mode:
`AUTH_SERVICE_MODE=api python3 -m services.auth_service.app.main`

## Endpoints
- `GET /health`
- `GET /auth/status`
- `POST /auth/bootstrap`