# market_data_gateway

## Purpose
Handles FYERS market data ingestion, normalization, Kafka topic preparation, Kafka publishing, and Redis hot-state caching for latest ticks and service status.

## Status
Scaffolded with stub feed, normalization, Kafka admin integration, Kafka producer integration, Redis hot-state caching, publishing logs, and API endpoints.

## Entry point
Stub mode:
`python3 -m services.market_data_gateway.app.main`

API mode:
`MDG_MODE=api python3 -m services.market_data_gateway.app.main`

## Endpoints
- `GET /health`
- `GET /gateway/status`
- `POST /gateway/emit-once`