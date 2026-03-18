#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

python - <<'PY' "$ROOT"
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / "services/execution_service/app/api.py"
text = path.read_text()

if '@app.get("/health")' in text and '@app.get("/execution-service/status")' in text and '@app.get("/execution-service/broker/health")' in text:
    print("[OK] Core endpoints already present")
    raise SystemExit(0)

block = '''
@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    replay_ready = True
    approved_loaded = 0
    active_order_count = _LIFECYCLE_STORE.active_order_count()
    message = "Execution service ready"
    open_position_count = len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0])

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
        active_order_count = status.active_order_count
        open_position_count = status.open_position_count
    except Exception as exc:
        replay_ready = False
        message = f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})"

    return {
        "service": "execution_service",
        "mode": settings.execution_service_mode,
        "broker": settings.execution_service_broker,
        "broker_adapter": broker_health.adapter,
        "broker_mode": broker_health.mode,
        "broker_ready": broker_health.ready,
        "replay_ready": replay_ready,
        "approved_loaded": approved_loaded,
        "orders_prepared": 0,
        "active_order_count": active_order_count,
        "open_position_count": open_position_count,
        "last_prepared_at": None,
        "message": message,
        "status": "ok" if broker_health.ready else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, object]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    try:
        status = build_execution_service().get_status()
        return {
            "service": status.service,
            "mode": status.mode,
            "broker": status.broker,
            "broker_adapter": status.broker_adapter,
            "broker_mode": status.broker_mode,
            "broker_ready": status.broker_ready,
            "replay_ready": status.replay_ready,
            "approved_loaded": status.approved_loaded,
            "orders_prepared": status.orders_prepared,
            "active_order_count": status.active_order_count,
            "open_position_count": status.open_position_count,
            "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
            "message": status.message,
        }
    except Exception as exc:
        return {
            "service": "execution_service",
            "mode": settings.execution_service_mode,
            "broker": settings.execution_service_broker,
            "broker_adapter": broker_health.adapter,
            "broker_mode": broker_health.mode,
            "broker_ready": broker_health.ready,
            "replay_ready": False,
            "approved_loaded": 0,
            "orders_prepared": 0,
            "active_order_count": _LIFECYCLE_STORE.active_order_count(),
            "open_position_count": len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0]),
            "last_prepared_at": None,
            "message": f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, object]:
    health = build_lifecycle_only_service().get_broker_health()
    return {
        "broker": health.broker,
        "adapter": health.adapter,
        "mode": health.mode,
        "ready": health.ready,
        "has_client_id": health.has_client_id,
        "has_access_token": health.has_access_token,
        "checked_at": health.checked_at.isoformat(),
        "message": health.message,
    }


'''

marker = '@app.post("/execution-service/marks")'
if marker not in text:
    raise SystemExit("Could not find insertion point in api.py")

text = text.replace(marker, block + "\n" + marker, 1)
path.write_text(text)
print("[OK] Restored /health, /execution-service/status, /execution-service/broker/health")
PY