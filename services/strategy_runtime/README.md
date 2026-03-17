# strategy_runtime

## Purpose
Reads indicator replay data from PostgreSQL and evaluates a stub strategy over it.

## Status
Scaffolded with replay-reader integration, strategy processor, evaluation service, and API endpoints.

## Entry point
Stub mode:
`python3 -m services.strategy_runtime.app.main`

API mode:
`STRATEGY_RUNTIME_MODE=api python3 -m services.strategy_runtime.app.main`

## Endpoints
- `GET /health`
- `GET /strategy-runtime/status`
- `POST /strategy-runtime/evaluate-once`