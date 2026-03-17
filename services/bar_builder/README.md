# bar_builder

## Purpose
Consumes tick events from Kafka, maintains open 1-minute bars, publishes open and closed bar events, caches hot bar state in Redis, persists closed bars to PostgreSQL, and exposes replayable closed-bar data.

## Status
Scaffolded with Kafka consumer integration, stateful tick-to-bar aggregation, closed-bar publishing flow, Redis hot-state caching, PostgreSQL closed-bar persistence, replay endpoints, and API endpoints.

## Entry point
Stub mode:
`python3 -m services.bar_builder.app.main`

API mode:
`BAR_BUILDER_MODE=api python3 -m services.bar_builder.app.main`

## Endpoints
- `GET /health`
- `GET /bar-builder/status`
- `POST /bar-builder/consume-once`
- `GET /bar-builder/replay/status`
- `GET /bar-builder/replay/closed-bars`