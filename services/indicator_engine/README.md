# indicator_engine

## Purpose
Consumes closed bars, produces indicator events, caches latest indicator state in Redis, persists indicator values to PostgreSQL, and exposes replayable indicator data.

## Status
Scaffolded with Kafka consumer integration, closed-bar processing, indicator publishing, Redis hot-state caching, PostgreSQL persistence, replay endpoints, and API endpoints.

## Entry point
Stub mode:
`python3 -m services.indicator_engine.app.main`

API mode:
`INDICATOR_ENGINE_MODE=api python3 -m services.indicator_engine.app.main`

## Endpoints
- `GET /health`
- `GET /indicator-engine/status`
- `POST /indicator-engine/consume-once`
- `GET /indicator-engine/replay/status`
- `GET /indicator-engine/replay/indicators`