from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.execution_service.app.models import BrokerPlaceOrderRequest
from services.execution_service.app.positions import PositionSnapshot


@dataclass(slots=True)
class ExecutionRiskDecision:
    allowed: bool
    reason: str
    code: str


class ExecutionRiskGuard:
    def __init__(
        self,
        *,
        max_order_quantity: int = 1,
        max_symbol_position_quantity: int = 1,
        max_open_positions: int = 5,
    ) -> None:
        self._max_order_quantity = max_order_quantity
        self._max_symbol_position_quantity = max_symbol_position_quantity
        self._max_open_positions = max_open_positions

    def evaluate_order(
        self,
        *,
        request: BrokerPlaceOrderRequest,
        positions: Iterable[PositionSnapshot],
    ) -> ExecutionRiskDecision:
        if request.quantity <= 0:
            return ExecutionRiskDecision(
                allowed=False,
                reason="Order quantity must be positive",
                code="invalid_quantity",
            )

        if request.quantity > self._max_order_quantity:
            return ExecutionRiskDecision(
                allowed=False,
                reason=(
                    f"Order quantity {request.quantity} exceeds "
                    f"max_order_quantity {self._max_order_quantity}"
                ),
                code="max_order_quantity_exceeded",
            )

        positions_list = list(positions)
        open_positions = [p for p in positions_list if p.net_quantity != 0]
        symbol_position = next((p for p in positions_list if p.symbol == request.symbol), None)

        if symbol_position is None:
            current_symbol_qty = 0
        else:
            current_symbol_qty = symbol_position.net_quantity

        signed_request_qty = request.quantity if request.side == "BUY" else -request.quantity
        projected_symbol_qty = current_symbol_qty + signed_request_qty

        if abs(projected_symbol_qty) > self._max_symbol_position_quantity:
            return ExecutionRiskDecision(
                allowed=False,
                reason=(
                    f"Projected position {projected_symbol_qty} for {request.symbol} exceeds "
                    f"max_symbol_position_quantity {self._max_symbol_position_quantity}"
                ),
                code="max_symbol_position_quantity_exceeded",
            )

        symbol_is_currently_flat = current_symbol_qty == 0
        opens_new_symbol_position = symbol_is_currently_flat and projected_symbol_qty != 0
        if opens_new_symbol_position and len(open_positions) >= self._max_open_positions:
            return ExecutionRiskDecision(
                allowed=False,
                reason=(
                    f"Open position limit reached: {len(open_positions)} >= "
                    f"{self._max_open_positions}"
                ),
                code="max_open_positions_exceeded",
            )

        return ExecutionRiskDecision(
            allowed=True,
            reason="Execution risk checks passed",
            code="allowed",
        )
