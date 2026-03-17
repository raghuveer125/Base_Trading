from __future__ import annotations

from typing import Any

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
)
from shared.config.settings import Settings
from shared.logging.logger import get_logger


class FyersBrokerAdapter(BrokerAdapter):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("execution_service.brokers.fyers")

    def adapter_name(self) -> str:
        return self._settings.execution_service_broker

    def is_live(self) -> bool:
        return self._settings.execution_service_broker.strip().lower() == "fyers_live"

    def health_check(self) -> BrokerHealth:
        has_client_id = bool(self._settings.fyers_client_id.strip())
        has_access_token = bool(self._settings.fyers_access_token.strip())

        ready = has_client_id and has_access_token
        mode = "live" if self.is_live() else "stub"
        message = "FYERS broker adapter ready" if ready else "FYERS broker adapter missing credentials"

        self._logger.info(
            "broker_health_check",
            broker=self.adapter_name(),
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
        )

        return BrokerHealth(
            broker=self.adapter_name(),
            adapter="fyers",
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
            message=message,
        )

    def _map_side(self, side: str) -> int:
        return 1 if side.upper() == "BUY" else -1

    def _map_order_type(self, order_type: str) -> int:
        normalized = order_type.upper()
        mapping = {
            "LIMIT": 1,
            "MARKET": 2,
            "STOP": 3,
            "STOP_LIMIT": 4,
        }
        return mapping[normalized]

    def _build_payload(self, request: BrokerPlaceOrderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": request.symbol,
            "qty": request.quantity,
            "type": self._map_order_type(request.order_type),
            "side": self._map_side(request.side),
            "productType": request.product,
            "limitPrice": request.limit_price,
            "stopPrice": request.stop_price,
            "validity": request.validity,
            "disclosedQty": request.disclosed_qty,
            "offlineOrder": request.offline_order,
            "stopLoss": request.stop_loss,
            "takeProfit": request.take_profit,
            "orderTag": request.idempotency_key or request.correlation_id or "execution_service",
        }
        return payload

    def _extract_order_id(self, response: dict[str, Any]) -> str | None:
        candidates = [
            response.get("id"),
            response.get("order_id"),
            response.get("orderId"),
        ]
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend(
                [
                    data.get("id"),
                    data.get("order_id"),
                    data.get("orderId"),
                ]
            )
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return None

    def _is_success_response(self, response: dict[str, Any]) -> bool:
        if response.get("s") == "ok":
            return True
        if response.get("code") in {200, 201, 1101}:
            return True
        return False

    def _get_live_client(self) -> Any:
        try:
            from fyers_apiv3 import fyersModel
        except Exception as exc:
            raise RuntimeError("fyers_apiv3 package is not installed") from exc

        token = f"{self._settings.fyers_client_id}:{self._settings.fyers_access_token}"
        return fyersModel.FyersModel(
            client_id=self._settings.fyers_client_id,
            is_async=False,
            token=token,
            log_path="",
        )

    def _place_live_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        payload = self._build_payload(request)
        client = self._get_live_client()
        self._logger.info(
            "fyers_live_order_submit_started",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        raw_response = client.place_order(payload)
        if not isinstance(raw_response, dict):
            raw_response = {"raw": str(raw_response)}

        accepted = self._is_success_response(raw_response)
        external_order_id = self._extract_order_id(raw_response)
        status = "accepted" if accepted else "rejected"

        self._logger.info(
            "fyers_live_order_submit_finished",
            accepted=accepted,
            status=status,
            external_order_id=external_order_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )

        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=accepted,
            status=status,
            external_order_id=external_order_id,
            message=raw_response.get("message") or raw_response.get("msg") or "FYERS live order processed",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=raw_response,
        )

    def place_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        health = self.health_check()
        if not health.ready:
            return BrokerPlaceOrderResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="rejected",
                external_order_id=None,
                message="Broker credentials missing",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
            )

        if self.is_live():
            try:
                return self._place_live_order(request)
            except Exception as exc:
                self._logger.exception(
                    "fyers_live_order_submit_failed",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )
                return BrokerPlaceOrderResponse(
                    broker=self.adapter_name(),
                    adapter="fyers",
                    accepted=False,
                    status="error",
                    external_order_id=None,
                    message=f"FYERS live order failed: {exc.__class__.__name__}: {exc}",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )

        synthetic_id = (
            f"stub-{request.symbol.replace(':', '_')}-"
            f"{request.side.lower()}-{request.quantity}-"
            f"{request.idempotency_key or 'na'}"
        )
        self._logger.info(
            "fyers_stub_order_accepted",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            product=request.product,
            external_order_id=synthetic_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id=synthetic_id,
            message="Stub broker accepted order",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=self._build_payload(request),
        )
