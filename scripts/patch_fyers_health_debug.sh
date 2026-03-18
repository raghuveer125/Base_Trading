#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

python - <<'PY' "$ROOT"
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / "services/execution_service/app/api.py"
text = path.read_text()

start = text.find('@app.get("/health")')
if start == -1:
    raise SystemExit('Could not find /health endpoint')

end_marker = '@app.post("/execution-service/marks")'
end = text.find(end_marker, start)
if end == -1:
    raise SystemExit('Could not find insertion boundary after health endpoints')

replacement = '''@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()

    broker_payload = {
        "adapter": "unknown",
        "mode": "unknown",
        "ready": False,
        "has_client_id": False,
        "has_access_token": False,
        "message": "Broker health not checked",
        "error_type": None,
        "error": None,
    }

    replay_ready = True
    approved_loaded = 0
    active_order_count = _LIFECYCLE_STORE.active_order_count()
    open_position_count = len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0])
    message = "Execution service ready"

    try:
        broker_adapter = build_broker_adapter(settings=settings)
        broker_health = broker_adapter.health_check()
        broker_payload.update(
            {
                "adapter": broker_health.adapter,
                "mode": broker_health.mode,
                "ready": broker_health.ready,
                "has_client_id": broker_health.has_client_id,
                "has_access_token": broker_health.has_access_token,
                "message": broker_health.message,
            }
        )
    except Exception as exc:
        broker_payload.update(
            {
                "message": f"Broker health check failed: {exc}",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
        active_order_count = status.active_order_count
        open_position_count = status.open_position_count
        message = status.message
    except Exception as exc:
        replay_ready = False
        message = f"Execution service degraded: {exc.__class__.__name__}: {exc}"

    return {
        "service": "execution_service",
        "mode": settings.execution_service_mode,
        "broker": settings.execution_service_broker,
        "broker_adapter": broker_payload["adapter"],
        "broker_mode": broker_payload["mode"],
        "broker_ready": broker_payload["ready"],
        "broker_has_client_id": broker_payload["has_client_id"],
        "broker_has_access_token": broker_payload["has_access_token"],
        "broker_error_type": broker_payload["error_type"],
        "broker_error": broker_payload["error"],
        "replay_ready": replay_ready,
        "approved_loaded": approved_loaded,
        "orders_prepared": 0,
        "active_order_count": active_order_count,
        "open_position_count": open_position_count,
        "last_prepared_at": None,
        "message": message,
        "status": "ok" if broker_payload["ready"] else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, object]:
    settings = get_settings()

    broker_payload = {
        "adapter": "unknown",
        "mode": "unknown",
        "ready": False,
        "has_client_id": False,
        "has_access_token": False,
        "message": "Broker health not checked",
        "error_type": None,
        "error": None,
    }

    try:
        broker_adapter = build_broker_adapter(settings=settings)
        broker_health = broker_adapter.health_check()
        broker_payload.update(
            {
                "adapter": broker_health.adapter,
                "mode": broker_health.mode,
                "ready": broker_health.ready,
                "has_client_id": broker_health.has_client_id,
                "has_access_token": broker_health.has_access_token,
                "message": broker_health.message,
            }
        )
    except Exception as exc:
        broker_payload.update(
            {
                "message": f"Broker health check failed: {exc}",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        status = build_execution_service().get_status()
        return {
            "service": status.service,
            "mode": status.mode,
            "broker": status.broker,
            "broker_adapter": status.broker_adapter,
            "broker_mode": status.broker_mode,
            "broker_ready": status.broker_ready,
            "broker_has_client_id": broker_payload["has_client_id"],
            "broker_has_access_token": broker_payload["has_access_token"],
            "broker_error_type": broker_payload["error_type"],
            "broker_error": broker_payload["error"],
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
            "broker_adapter": broker_payload["adapter"],
            "broker_mode": broker_payload["mode"],
            "broker_ready": broker_payload["ready"],
            "broker_has_client_id": broker_payload["has_client_id"],
            "broker_has_access_token": broker_payload["has_access_token"],
            "broker_error_type": broker_payload["error_type"] or exc.__class__.__name__,
            "broker_error": broker_payload["error"] or str(exc),
            "replay_ready": False,
            "approved_loaded": 0,
            "orders_prepared": 0,
            "active_order_count": _LIFECYCLE_STORE.active_order_count(),
            "open_position_count": len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0]),
            "last_prepared_at": None,
            "message": f"Execution service degraded: {exc.__class__.__name__}: {exc}",
        }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, object]:
    settings = get_settings()
    try:
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
            "error_type": None,
            "error": None,
        }
    except Exception as exc:
        return {
            "broker": settings.execution_service_broker,
            "adapter": "unknown",
            "mode": "unknown",
            "ready": False,
            "has_client_id": bool(getattr(settings, "fyers_client_id", "")),
            "has_access_token": bool(getattr(settings, "fyers_access_token", "")),
            "checked_at": None,
            "message": f"Broker health check failed: {exc}",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }


'''
new_text = text[:start] + replacement + "\n" + text[end:]
path.write_text(new_text)
print("[OK] FYERS health debug patch applied")
PY